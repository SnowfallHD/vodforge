"""Independent local telemetry suite, lifetime and synthetic audit evidence.

No production D1, deployed ingestion, native interface or audible output claim.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .pipeline_interaction import _number, load_observation
from .source_suite_interaction import _read
from .transaction_interaction import _trace

CATALOG = json.loads(Path(__file__).with_name("telemetry_catalog.json").read_text())
TELEMETRY_CONTRACTS = {
    "unit_static.telemetry_backend_suite": "clean-backend-per-case-suite-v1",
    "unit_static.telemetry_local_contract": "loopback-worker-d1-lifetime-v1",
    "unit_static.telemetry_isolation": "isolated-telemetry-audit-control-v1",
}
SCOPES = {
    "unit_static.telemetry_backend_suite": "clean site source and local Vitest cases; no deployed Worker or production D1",
    "unit_static.telemetry_local_contract": "real desktop HTTP and local Worker/D1 with controlled providers; no production D1, native or audible output",
    "unit_static.telemetry_isolation": "synthetic audit dispatch only; no DNS, sockets or HTTP network I/O",
}


def _site(value):
    if not isinstance(value, dict):
        return False
    m = value.get("source_manifest", {})
    payload = {k: m.get(k) for k in ("format", "files")}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return (
        value.get("branch") == "main"
        and value.get("status_porcelain") == []
        and isinstance(value.get("commit"), str)
        and len(value["commit"]) == 40
        and isinstance(value.get("root"), str)
        and Path(value["root"]).is_absolute()
        and m.get("format") == "vodforge-source-files-v1"
        and isinstance(m.get("files"), dict)
        and sorted(m["files"]) == CATALOG["site_source_paths"]
        and all(
            v.get("kind") == "file"
            and isinstance(v.get("sha256"), str)
            and len(v["sha256"]) == 64
            for v in m["files"].values()
        )
        and m.get("sha256") == value.get("source_manifest_sha256") == digest
    )


def _result(r):
    return (
        isinstance(r, dict)
        and r.get("returncode") == 0
        and r.get("timed_out") is False
        and r.get("unavailable") is False
        and _number(r.get("duration_seconds"))
        and r["duration_seconds"] > 0
        and isinstance(r.get("stdout"), str)
        and isinstance(r.get("stderr"), str)
    )


def _backend(raw, root, check):
    rows = _trace(
        raw, "trace", ["before_backend", "backend_returned", "site_reobserved"], check
    )
    if rows is None:
        return
    before, during, after = rows
    check(
        "before",
        "clean_source_and_absent_report",
        "site" in before and "report" in before,
        _site(before.get("site"))
        and before.get("report")
        == {"path": str(root / "backend-cases.json"), "exists": False},
        "Clean main site source is content identified and this suite report is absent on entry",
    )
    report = _read(raw.get("test_report"), root, check, "during", "backend_report")
    command = during.get("result")
    check(
        "during",
        "exact_successful_execution",
        isinstance(command, dict),
        _result(command)
        and command.get("command")
        == [
            "npm",
            "test",
            "--",
            "--reporter=json",
            "--outputFile=" + str(root / "backend-cases.json"),
        ]
        and command["duration_seconds"]
        <= during["elapsed_seconds"] - before["elapsed_seconds"] + 0.02,
        "Actual npm/Vitest command returned successfully within the observed execution interval",
    )
    if isinstance(report, dict):
        suites = report.get("testResults", [])
        cases = [
            Path(s["name"]).relative_to(before["site"]["root"]).as_posix()
            + "::"
            + c["fullName"]
            for s in suites
            for c in s["assertionResults"]
        ]
        check(
            "during",
            "complete_reviewed_cases",
            isinstance(suites, list),
            sorted(cases) == CATALOG["backend_cases"]
            and report.get("success") is True
            and report.get("numTotalTests")
            == report.get("numPassedTests")
            == len(cases)
            == 263
            and all(
                report.get(k) == 0
                for k in (
                    "numFailedTests",
                    "numPendingTests",
                    "numTodoTests",
                    "numFailedTestSuites",
                    "numPendingTestSuites",
                )
            )
            and all(
                s.get("status") == "passed"
                and s.get("message") == ""
                and s["endTime"] >= s["startTime"]
                and all(
                    c.get("status") == "passed" and c.get("failureMessages") == []
                    for c in s["assertionResults"]
                )
                for s in suites
            ),
            "Exactly 263 reviewed per-case outcomes pass with exact reviewed name multiplicities and no omissions, substitutions or skips",
        )
    else:
        check(
            "during",
            "complete_reviewed_cases",
            False,
            False,
            "Missing bound per-case report",
        )
    check(
        "after",
        "unchanged_clean_site_and_report",
        "site" in after and "report" in after,
        _site(after.get("site"))
        and after.get("site") == before.get("site")
        and after.get("report") == during.get("report") == raw.get("test_report"),
        "Clean site identity and actual report remain unchanged after suite execution",
    )


def _snapshot(v):
    return (
        isinstance(v, dict)
        and set(v) == {"installations", "clients", "events"}
        and all(isinstance(v[k], list) for k in v)
    )


def _identity(v):
    return (
        _snapshot(v)
        and len(v["installations"]) == len(v["clients"]) == 1
        and v["installations"][0]["current_app_version"] == "0.1.8"
        and v["installations"][0]["install_id"] == v["clients"][0]["install_id"]
        and v["installations"][0]["telemetry_owner"] == v["clients"][0]["credential_id"]
        and v["clients"][0]["revoked_at"] is None
    )


def _local(raw, root, check):
    rows = _trace(
        raw,
        "trace",
        [
            "before_local_contract",
            "worker_ready",
            "consent_denied",
            "launches_completed",
            "session_reopened",
            "events_delivered",
            "permission_withdrawn",
            "ownership_verified",
            "worker_closed",
        ],
        check,
    )
    if rows is None:
        return
    before, ready, denied, launch, reopen, delivery, withdrawn, owned, after = rows
    check(
        "before",
        "clean_fresh_client",
        "site" in before and "client_exists" in before,
        _site(before.get("site")) and before.get("client_exists") is False,
        "Clean content identified site and absent desktop credential profile precede the contract",
    )
    endpoint = urlsplit(ready.get("endpoint", ""))
    check(
        "before",
        "loopback_empty_d1",
        "endpoint" in ready and "snapshot" in ready,
        endpoint.scheme == "http"
        and endpoint.hostname == "127.0.0.1"
        and endpoint.port is not None
        and endpoint.path == "/"
        and endpoint.username is None
        and endpoint.password is None
        and ready.get("snapshot") == {"installations": [], "clients": [], "events": []},
        "Real Worker endpoint is pinned to an empty private loopback D1",
    )
    refs = ready.get("failure_workers")
    check(
        "during",
        "both_real_failure_workers",
        isinstance(refs, list),
        isinstance(refs, list) and [x.get("suffix") for x in refs] == ["404", "500"],
        "Both real worker HTTP failure constituents are retained",
    )
    if isinstance(refs, list):
        for ref in refs:
            suffix = ref.get("suffix")
            worker = _read(
                ref.get("worker"), root.parent, check, "during", "worker_" + str(suffix)
            )
            check(
                "during",
                "worker_diagnostic_" + str(suffix),
                isinstance(worker, dict),
                isinstance(worker, dict)
                and worker.get("failure_diagnostic") == ref.get("diagnostic")
                and worker.get("case_id") == "telemetry-failure-" + str(suffix)
                and worker.get("media_output_count") == 0
                and worker.get("staging_entries_after") == []
                and ref["diagnostic"].get("http_status") == int(suffix)
                and ref["diagnostic"].get("error_type") == "HTTPError"
                and ref["diagnostic"].get("stage") == "analysis",
                "Actual failed worker diagnostics agree with bound raw content and publish no media or staging residue",
            )
    check(
        "during",
        "denial_is_silent",
        all(k in denied for k in ("unknown_launch", "refused_launch", "snapshot")),
        denied.get("unknown_launch") is False
        and denied.get("refused_launch") is False
        and denied.get("snapshot") == ready.get("snapshot"),
        "Unknown and refused consent produce no installation, credential or event writes",
    )
    l, r = launch.get("snapshot"), reopen.get("snapshot")
    check(
        "during",
        "durable_session_identity",
        _identity(l) and _identity(r),
        _identity(l)
        and _identity(r)
        and l["clients"] == r["clients"]
        and l["events"] == r["events"]
        and len(l["events"]) == 1
        and l["events"][0]["event_name"] == "client_update"
        and l["events"][0]["from_version"] == "0.1.7"
        and l["events"][0]["to_version"] == "0.1.8"
        and l["installations"][0]["first_launched_at"]
        == r["installations"][0]["first_launched_at"]
        and r["installations"][0]["last_seen_at"]
        > l["installations"][0]["last_seen_at"],
        "Reopening advances last seen while preserving first launch, sole credential and exactly one version transition",
    )
    snap, emitted = delivery.get("snapshot"), delivery.get("delivered")
    typed = (
        _identity(snap)
        and isinstance(emitted, list)
        and all(isinstance(v, dict) for v in emitted)
    )
    check(
        "during",
        "complete_event_roster",
        typed,
        typed
        and sorted(
            json.dumps(
                [
                    v.get(k)
                    for k in (
                        "event_name",
                        "run_kind",
                        "output_type",
                        "feature",
                        "action",
                    )
                ]
            )
            for v in emitted
        )
        == CATALOG["event_signatures"]
        and len(emitted) == 395
        and len(snap["events"]) == 396
        and len({v.get("event_id") for v in emitted}) == 395
        and len({v.get("event_id") for v in snap["events"]}) == 396
        and "PRIVATE" not in json.dumps(emitted)
        and "PRIVATE" not in json.dumps(snap),
        "All 395 reviewed producer signatures and one update are uniquely stored; controlled private canaries are absent",
    )
    if typed:
        stored = {v["event_id"]: v for v in snap["events"]}
        expected_ids = {v["event_id"] for v in emitted} | {l["events"][0]["event_id"]}
        check(
            "during",
            "no_missing_or_extra_ids",
            True,
            set(stored) == expected_ids
            and stored[l["events"][0]["event_id"]] == l["events"][0],
            "Stored event IDs are exactly the delivered set and the single unchanged update",
        )
        for i, v in enumerate(emitted):
            actual = stored.get(v["event_id"], {})
            valid = (
                v.get("install_id") == r["installations"][0]["install_id"]
                and v.get("schema_version") == 2
                and all(
                    actual.get(k) == v.get(k)
                    for k in (
                        "event_name",
                        "run_kind",
                        "output_type",
                        "attempt_id",
                        "retry_of",
                        "feature",
                        "action",
                        "schema_version",
                    )
                )
                and isinstance(v.get("dimensions"), dict)
                and json.loads(actual.get("dimensions", "null")) == v["dimensions"]
                and abs(
                    (
                        datetime.fromisoformat(
                            actual["occurred_at"].replace("Z", "+00:00")
                        )
                        - datetime.fromisoformat(
                            v["occurred_at"].replace("Z", "+00:00")
                        )
                    ).total_seconds()
                )
                < 0.001
                and (
                    "failure_detail" not in v
                    or json.loads(actual.get("failure_detail", "null"))
                    == v["failure_detail"]
                    and actual.get("failure_reason") == v.get("failure_reason")
                )
            )
            check(
                "during",
                "stored_payload_" + str(i),
                True,
                valid,
                "Actual D1 fields and timestamp normalization agree with this emitted payload",
            )
        failures = [v for v in emitted if v.get("event_name") == "run_failed"]
        check(
            "during",
            "both_bounded_failure_causes",
            True,
            sorted(
                (
                    v.get("failure_reason"),
                    v.get("failure_detail", {}).get("http_status"),
                )
                for v in failures
            )
            == [("source_unavailable", 404), ("unknown", 500)]
            and all(
                v["failure_detail"].get("error_type") == "HTTPError"
                and v["failure_detail"].get("stage") == "analysis"
                for v in failures
            ),
            "Real 404 and 500 causes survive local transport without narrowing the unknown 500 reason",
        )
    check(
        "after",
        "withdrawal_prevents_writes",
        all(k in withdrawn for k in ("launch", "event", "snapshot")),
        withdrawn.get("launch") is False
        and withdrawn.get("event") is False
        and withdrawn.get("snapshot") == snap,
        "Original permission withdrawal refuses both launch and event and leaves D1 exactly unchanged",
    )
    cases = owned.get("cases")
    origins = [
        "fresh",
        "claim",
        "cloud_seen",
        "cloud_click",
        "legacy_launch",
        "waitlist",
    ]
    check(
        "after",
        "all_ownership_entry_points",
        isinstance(cases, list),
        isinstance(cases, list)
        and cases
        == [
            {
                "origin": o,
                "statuses": [200, 200, 409, 401],
                "legacy": {"unchanged": True, "accepted": 0},
                "client_count": 1,
            }
            for o in origins
        ],
        "All six entry points preserve one credential, reject second actor and invalid credential, and exclude legacy writes",
    )
    receipt = _read(raw.get("receipt"), root, check, "after", "d1_receipt")
    check(
        "after",
        "durable_receipt_matches",
        isinstance(receipt, dict),
        isinstance(snap, dict)
        and receipt
        == {**snap, "site_commit": before["site"]["commit"], "ownership_matrix": cases},
        "Closed content-bound D1 receipt agrees with every observed event and ownership result",
    )
    check(
        "after",
        "worker_closed_source_unchanged",
        "returncode" in after and "site" in after,
        after.get("returncode") == 0
        and _site(after.get("site"))
        and after.get("site") == delivery.get("site") == before.get("site"),
        "Owned Worker exits normally and site source identity remains unchanged",
    )


def _isolation(raw, root, check):
    rows = _trace(
        raw, "trace", ["before_control", "control_returned", "parent_reobserved"], check
    )
    if rows is None:
        return
    before, during, after = rows
    state = {"guard_installed": True, "disabled": "1", "parent_attempts": []}
    for phase, row in (("before", before), ("after", after)):
        check(
            phase,
            "parent_isolated",
            all(k in row for k in state),
            all(row.get(k) == v for k, v in state.items()),
            "Parent remains guarded, telemetry disabled, with zero real production attempts",
        )
    command = _read(raw.get("control"), root, check, "during", "audit_control")
    check(
        "during",
        "isolated_child_success",
        isinstance(command, dict),
        _result(command)
        and command == during.get("command_result")
        and len(command.get("command", [])) == 3
        and command["command"][1] == "-c"
        and "sys.audit(" in command["command"][2]
        and "urlopen(" not in command["command"][2]
        and command["duration_seconds"]
        <= during["elapsed_seconds"] - before["elapsed_seconds"] + 0.02,
        "Private child dispatches synthetic audit events, returns normally, and has an exact content-bound command receipt",
    )
    if not isinstance(command, dict):
        return
    observed = json.loads(command.get("stdout", "null"))
    specs = [
        ("urllib.Request", "https://getvodforge.com/api/telemetry/v2/events"),
        ("urllib.Request", "https://events.heycatch.ai/ingest"),
        ("socket.getaddrinfo", "GETVODFORGE.COM"),
        ("socket.getaddrinfo", "sub.heycatch.ai"),
        ("urllib.Request", "http://127.0.0.1:1/fixture"),
        ("socket.getaddrinfo", "example.invalid"),
    ]
    calls = observed.get("rows") if isinstance(observed, dict) else None
    check(
        "during",
        "complete_audit_matrix",
        isinstance(calls, list),
        isinstance(calls, list)
        and observed.get("guard_installed") is True
        and [(v.get("event"), v.get("host")) for v in calls] == specs,
        "Exact production, uppercase, subdomain and safe loopback/invalid-host audit cases were dispatched",
    )
    if not isinstance(calls, list):
        return
    for i, call in enumerate(calls):
        timed = _number(call.get("entered")) and _number(call.get("returned"))
        check(
            "during",
            "audit_call_" + str(i),
            all(
                k in call
                for k in (
                    "entered",
                    "returned",
                    "before",
                    "after",
                    "exception_type",
                    "message",
                )
            ),
            timed
            and call["entered"] < call["returned"]
            and (i == 0 or calls[i - 1]["returned"] < call["entered"])
            and call.get("before") == ["production_telemetry_attempt"] * min(i, 4)
            and call.get("after") == ["production_telemetry_attempt"] * min(i + 1, 4)
            and call.get("exception_type") == ("RuntimeError" if i < 4 else None)
            and call.get("message")
            == (
                "Production telemetry forbidden in engineering harness" if i < 4 else ""
            ),
            "Forbidden synthetic events raise once and grow the marker count; allowed events are silent and do not change it",
        )


def evaluate_telemetry(scenario):
    raw, reason = load_observation(scenario)
    assertions = []

    def check(phase, name, present, valid, detail):
        assertions.append(
            {
                "phase": phase,
                "assertion": name,
                "status": "unproven"
                if not present
                else "passed"
                if valid
                else "failed",
                "evidence": detail,
            }
        )

    if raw is None:
        for phase in ("before", "during", "after"):
            check(phase, "raw_receipt_binding", False, False, reason)
    else:
        try:
            check(
                "before",
                "explicit_local_identity",
                all(k in raw for k in ("scenario_id", "contract", "scope")),
                raw.get("scenario_id") == scenario["id"]
                and raw.get("contract") == TELEMETRY_CONTRACTS[scenario["id"]]
                and raw.get("scope") == SCOPES[scenario["id"]],
                "Contract identity and bounded local execution scope match",
            )
            evaluator = (
                _backend
                if "backend" in scenario["id"]
                else _local
                if "local" in scenario["id"]
                else _isolation
            )
            evaluator(raw, Path(scenario["raw_result"]).parent, check)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError, OSError):
            check(
                "during",
                "observation_schema",
                False,
                False,
                "Missing or malformed telemetry observations",
            )
    phases = {}
    for phase in ("before", "during", "after"):
        states = [v["status"] for v in assertions if v["phase"] == phase]
        phases[phase] = (
            "failed"
            if "failed" in states
            else "unproven"
            if not states or "unproven" in states
            else "passed"
        )
    return {
        "status": "failed"
        if "failed" in phases.values()
        else "unproven"
        if "unproven" in phases.values()
        else "passed",
        "scenario_id": scenario["id"],
        "required_phases": list(phases),
        "phase_review": phases,
        "assertion_mapping": assertions,
        "domain_contract": TELEMETRY_CONTRACTS[scenario["id"]],
        "reason": "Local suite, HTTP/Worker/D1 and synthetic audit evidence only; no deployed ingestion, production D1, native or audible-output acceptance.",
    }
