"""Independent bounded log-sink and two-origin thumbnail observations.

Synthetic URL canaries and loopback authorities do not qualify external provider
networking, Windows ACLs, or a native interface.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import quote, urlsplit

from .pipeline_interaction import _number, load_observation
from .transaction_interaction import _file, _trace

SECURITY_CONTRACTS = {
    "security.url_secret_persistence": "controlled-url-secret-sinks-v1",
    "security.thumbnail_network_authority": "loopback-thumbnail-authority-v1",
}


def _secrets(raw, root, check):
    rows = _trace(
        raw, "trace", ["before_sinks", "sinks_closed", "durable_reobserved"], check
    )
    if rows is None:
        return
    before, during, after = rows
    names = [
        "batch-url-failures.txt",
        "activity.log",
        "diagnostics.log",
        "metadata/metadata.json",
    ]
    files = before.get("files")
    check(
        "before",
        "fresh_owned_sinks",
        isinstance(files, list),
        isinstance(files, list)
        and len(files) == 4
        and all(
            f == {"path": str(root / name), "exists": False}
            for f, name in zip(files, names)
        ),
        "All four controlled sink files are absent before invoking production writers",
    )
    check(
        "before",
        "synthetic_secret_scope",
        all(k in raw for k in ("input_url", "canary", "os_name", "scope")),
        raw.get("canary") == "TOPSECRET-HARNESS-CANARY"
        and raw.get("input_url")
        == "https://user:pass@example.invalid/media?id=1&token=TOPSECRET-HARNESS-CANARY#fragment"
        and raw.get("os_name") == "posix"
        and raw.get("scope") == "synthetic canary sinks and POSIX log modes",
        "This observation tests a synthetic credential/query/fragment canary and POSIX log permissions only",
    )
    keys = [
        "history_activity",
        "history_url",
        "persistent_activity",
        "batch_failure",
        "diagnostic",
        "compact_metadata",
    ]
    texts = during.get("text")
    for name in keys:
        text = texts.get(name) if isinstance(texts, dict) else None
        check(
            "during",
            "safe_identity_" + name,
            isinstance(text, str),
            isinstance(text, str)
            and "https://example.invalid/media" in text
            and all(
                token not in text
                for token in (
                    "TOPSECRET-HARNESS-CANARY",
                    "user:pass",
                    "#fragment",
                    "?id=1",
                )
            ),
            "Actual sink text keeps useful source identity and removes credential, query and fragment content",
        )
    written = during.get("files")
    typed = isinstance(written, list) and len(written) == 4
    persisted_keys = [
        "batch_failure",
        "persistent_activity",
        "diagnostic",
        "compact_metadata",
    ]
    for i, name in enumerate(names):
        f = written[i] if typed else None
        text = texts.get(persisted_keys[i]) if isinstance(texts, dict) else None
        check(
            "during",
            "content_bound_" + name,
            isinstance(f, dict) and isinstance(text, str),
            _file(f)
            and isinstance(text, str)
            and f["path"] == str(root / name)
            and f["size_bytes"] == len(text.encode())
            and f["sha256"] == hashlib.sha256(text.encode()).hexdigest()
            and (i == 3 or f.get("mode") == 0o600),
            "Observed closed file size/hash bind its exact text; three private logs have mode 0600",
        )
    check(
        "after",
        "unchanged_durable_sinks",
        all(k in after for k in ("files", "text")),
        typed
        and after.get("files") == written
        and isinstance(texts, dict)
        and after.get("text") == {k: texts.get(k) for k in persisted_keys},
        "Re-reading all four durable files after closure preserves their exact sanitized content",
    )


def _origin(url):
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def _snapshot(v, origin):
    return (
        isinstance(v, dict)
        and v.get("origin") == origin
        and isinstance(v.get("requests"), dict)
        and type(v.get("total_requests")) is int
        and isinstance(v.get("responses"), list)
        and isinstance(v.get("bytes_sent"), dict)
    )


def _network(raw, root, check):
    rows = _trace(
        raw, "trace", ["before_fetches", "calls_returned", "target_closed"], check
    )
    if rows is None:
        return
    before, during, after = rows
    source, target = raw.get("source_url"), raw.get("target_url")
    if not isinstance(source, str) or not isinstance(target, str):
        check("before", "origin_binding", False, False, "Missing origins")
        return
    so, to = _origin(source), _origin(target)
    parsed = [urlsplit(u) for u in (source, target)]
    check(
        "before",
        "loopback_authority_scope",
        "scope" in raw,
        raw.get("scope") == "two loopback HTTP origins; no external authority requests"
        and so != to
        and all(
            p.scheme == "http"
            and p.hostname == "127.0.0.1"
            and p.port
            and p.username is None
            and p.password is None
            for p in parsed
        )
        and parsed[0].path == "/page/normal"
        and parsed[1].path == "/thumbnail.jpg",
        "Explicit source and forbidden target are distinct HTTP loopback ports; no external-provider claim",
    )
    check(
        "before",
        "fresh_target",
        _snapshot(before.get("source"), so) and _snapshot(before.get("target"), to),
        _snapshot(before.get("source"), so)
        and _snapshot(before.get("target"), to)
        and before["target"]["total_requests"] == 0
        and before["target"]["requests"] == {}
        and before["target"]["responses"] == []
        and before["target"]["bytes_sent"] == {},
        "The forbidden target has no requests, responses or payload before the three fetch attempts",
    )
    fixture = raw.get("fixture")
    check(
        "before",
        "fixture_payload",
        isinstance(fixture, dict),
        _file(fixture)
        and fixture.get("path") == str(root.parent.parent / "fixtures/thumbnail.jpg"),
        "Known JPEG fixture size/hash is observed independently of the fetch return",
    )
    calls = raw.get("calls")
    typed = (
        isinstance(calls, list)
        and len(calls) == 3
        and all(isinstance(c, dict) for c in calls)
    )
    check(
        "during",
        "complete_call_sequence",
        typed,
        typed
        and [c.get("label") for c in calls]
        == ["same_origin", "direct_cross_origin", "redirect_cross_origin"],
        "Same-origin, direct foreign and redirected foreign fetch calls each have an actual result",
    )
    if not typed:
        return
    expected_urls = [
        so + "/thumbnail.jpg",
        target,
        so + "/redirect/thumbnail?to=" + quote(target, safe=""),
    ]
    for i, c in enumerate(calls):
        label = ["same_origin", "direct_cross_origin", "redirect_cross_origin"][i]
        timed = _number(c.get("entered_seconds")) and _number(c.get("returned_seconds"))
        check(
            "during",
            label + "_binding",
            timed and all(k in c for k in ("url", "source_url", "timeout_seconds")),
            timed
            and c["url"] == expected_urls[i]
            and c["source_url"] == source
            and c["timeout_seconds"] == 5
            and before["elapsed_seconds"]
            < c["entered_seconds"]
            < c["returned_seconds"]
            < during["elapsed_seconds"]
            and (i == 0 or calls[i - 1]["returned_seconds"] < c["entered_seconds"]),
            "Observed call parameters and monotonic interval bind the result to the declared authority",
        )
        sb, sa, tb, ta = [
            c.get(k)
            for k in ("source_before", "source_after", "target_before", "target_after")
        ]
        valid_snaps = (
            _snapshot(sb, so)
            and _snapshot(sa, so)
            and _snapshot(tb, to)
            and _snapshot(ta, to)
        )
        check(
            "during",
            label + "_request_ownership",
            valid_snaps,
            valid_snaps
            and tb == before["target"]
            and ta == tb
            and sb == (before["source"] if i == 0 else calls[i - 1]["source_after"])
            and sa["total_requests"] - sb["total_requests"] == (0 if i == 1 else 1)
            and (
                sa == sb
                if i == 1
                else sa["requests"].get(
                    "/thumbnail.jpg" if i == 0 else "/redirect/thumbnail", 0
                )
                - sb["requests"].get(
                    "/thumbnail.jpg" if i == 0 else "/redirect/thumbnail", 0
                )
                == 1
            )
            and (
                i == 1
                or len(sa["responses"]) == len(sb["responses"]) + 1
                and sa["responses"][-1].get("route")
                == ("/thumbnail.jpg" if i == 0 else "/redirect/thumbnail")
                and sa["responses"][-1].get("status") == (200 if i == 0 else 302)
            ),
            "Source request delta matches this attempt and the foreign target receives no request",
        )
        keys = ("exception_type", "payload_size", "payload_sha256", "rejection")
        check(
            "during",
            label + "_return",
            all(k in c for k in keys),
            (
                c.get("exception_type") is None
                and c.get("rejection") == ""
                and _file(fixture)
                and c.get("payload_size") == fixture["size_bytes"]
                and c.get("payload_sha256") == fixture["sha256"]
            )
            if i == 0
            else c.get("exception_type") == "RuntimeError"
            and "not trusted" in c.get("rejection", "")
            and c.get("payload_size") == 0
            and c.get("payload_sha256") == hashlib.sha256(b"").hexdigest(),
            "Allowed fetch returns exact known payload; both forbidden routes reject without returning bytes",
        )
    check(
        "after",
        "closed_target_stable",
        all(k in after for k in ("source", "target")),
        after.get("source") == during.get("source") == calls[-1].get("source_after")
        and after.get("target") == during.get("target") == before.get("target"),
        "After target server closure no late foreign request or source mutation appeared",
    )


def evaluate_security(scenario):
    raw, reason = load_observation(scenario)
    rows = []

    def check(phase, name, present, valid, detail):
        rows.append(
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
                "security_identity",
                "scenario_id" in raw and "contract" in raw,
                raw.get("scenario_id") == scenario["id"]
                and raw.get("contract") == SECURITY_CONTRACTS[scenario["id"]],
                "Explicit security component identity and contract match",
            )
            (_secrets if "secret" in scenario["id"] else _network)(
                raw, Path(scenario["raw_result"]).parent, check
            )
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            check(
                "during",
                "observation_schema",
                False,
                False,
                "Missing or malformed security observations",
            )
    phases = {}
    for phase in ("before", "during", "after"):
        states = [r["status"] for r in rows if r["phase"] == phase]
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
        "assertion_mapping": rows,
        "domain_contract": SECURITY_CONTRACTS[scenario["id"]],
        "reason": "Bounded synthetic sink/POSIX or loopback authority scope; separate native, ACL and external-provider acceptance required.",
    }
