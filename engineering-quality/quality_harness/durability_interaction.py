"""Optional sink recovery and exact private-copy mutation evidence, no native UX."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .pipeline_interaction import _contained, _number, load_observation
from .source_suite_interaction import _read
from .transaction_interaction import _file, _trace

CATALOG = json.loads(Path(__file__).with_name("mutation_catalog.json").read_text())
DURABILITY_CONTRACTS = {
    "unit_static.activity_log_failure_receipt": "optional-activity-failure-episodes-v1",
    "unit_static.bounded_mutation_history": "bounded-private-source-mutants-v1",
}
DIAGNOSTIC = "Persistent Activity storage is unavailable. Current-session activity remains visible, but Activity history may not survive an app restart."


def _activity(raw, root, check):
    rows = _trace(
        raw,
        "trace",
        [
            "before_failed_sink",
            "first_failure_observed",
            "durable_write_recovered",
            "new_failure_observed",
        ],
        check,
    )
    if rows is None:
        return
    before, failed, recovered, after = rows
    check(
        "before",
        "controlled_sink_scope",
        "scope" in raw,
        raw.get("scope")
        == "controlled directory refusal and durable log recovery; no native Activity UI",
        "Directory refusals and production durable sink only, not visible Activity presentation",
    )
    check(
        "before",
        "fresh_detached_sink",
        all(
            k in before
            for k in (
                "first_bad",
                "second_bad",
                "handle_none",
                "handle_path_none",
                "failure_reported",
                "receipts",
                "recovered_file",
                "recovered_text",
            )
        ),
        before.get("first_bad") is True
        and before.get("second_bad") is True
        and before.get("handle_none") is True
        and before.get("handle_path_none") is True
        and before.get("failure_reported") is False
        and before.get("receipts") == []
        and before.get("recovered_file")
        == {"path": str(root / "recovered-activity.log"), "exists": False}
        and before.get("recovered_text") is None,
        "Both refused targets are directories; no prior recovery file, stale handle or failure receipt",
    )
    check(
        "during",
        "single_refusal_episode",
        all(
            k in failed
            for k in (
                "receipts",
                "handle_none",
                "handle_path_none",
                "failure_reported",
                "recovered_file",
                "recovered_text",
            )
        ),
        failed.get("receipts") == [DIAGNOSTIC]
        and failed.get("handle_none") is True
        and failed.get("handle_path_none") is True
        and failed.get("failure_reported") is True
        and failed.get("recovered_file") == before.get("recovered_file")
        and failed.get("recovered_text") is None,
        "Prepare and append failures produce exactly one generic receipt and detach both handle fields",
    )
    file = recovered.get("recovered_file")
    text = recovered.get("recovered_text")
    check(
        "during",
        "actual_durable_recovery",
        isinstance(file, dict) and isinstance(text, str),
        _file(file)
        and file["path"] == str(root / "recovered-activity.log")
        and file.get("mode") == 0o600
        and text == "durable activity recovered\n"
        and file["size_bytes"] == len(text.encode())
        and file["sha256"] == hashlib.sha256(text.encode()).hexdigest()
        and recovered.get("receipts") == [DIAGNOSTIC]
        and recovered.get("failure_reported") is False
        and recovered.get("handle_none") is True
        and recovered.get("handle_path_none") is True,
        "Writable target receives exact durable bytes, is private and resets failure suppression after closure",
    )
    check(
        "after",
        "new_episode_and_preserved_success",
        all(
            k in after
            for k in (
                "receipts",
                "handle_none",
                "handle_path_none",
                "failure_reported",
                "recovered_file",
                "recovered_text",
            )
        ),
        after.get("receipts") == [DIAGNOSTIC, DIAGNOSTIC]
        and after.get("handle_none") is True
        and after.get("handle_path_none") is True
        and after.get("failure_reported") is True
        and after.get("recovered_file") == file
        and after.get("recovered_text") == text,
        "A new failure after recovery receives a second generic receipt without modifying successful durable content",
    )


def _source(ref, root, check, name):
    valid = _file(ref) and _contained(ref.get("path", ""), str(root))
    check(
        "during",
        name + "_source_location",
        isinstance(ref, dict),
        valid,
        "Bounded copied source file belongs to this private mutation case",
    )
    if not valid:
        return None
    try:
        p = Path(ref["path"])
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("unbounded file")
        data = p.read_bytes()
        if (
            len(data) != ref["size_bytes"]
            or hashlib.sha256(data).hexdigest() != ref["sha256"]
        ):
            raise ValueError("changed source")
        return data.decode()
    except (OSError, ValueError):
        check(
            "during",
            name + "_source_content",
            False,
            False,
            "Missing or changed copied source",
        )
        return None


def _nodes(xml):
    cases = xml.findall(".//testcase") if xml is not None else []
    return cases, [
        c.get("classname", "").replace(".", "/") + ".py::" + c.get("name", "")
        for c in cases
    ]


def _result(result, expected):
    return (
        isinstance(result, dict)
        and result.get("returncode") == expected
        and result.get("timed_out") is False
        and result.get("unavailable") is False
        and _number(result.get("duration_seconds"))
        and result["duration_seconds"] > 0
    )


def _mutants(raw, root, check):
    rows = _trace(
        raw,
        "trace",
        ["before_baseline", "baseline_returned", "campaign_reobserved"],
        check,
    )
    if rows is None:
        return
    before, baseline, after = rows
    source = before.get("source")
    check(
        "before",
        "bounded_campaign_scope",
        "scope" in raw,
        raw.get("scope")
        == "nine explicit private-copy history/artwork mutations; not repository-wide quality",
        "Exactly nine reviewed source changes in disposable non-Git fixture copies",
    )
    check(
        "before",
        "unmodified_baseline_copy",
        isinstance(source, dict) and isinstance(before.get("copied_source"), dict),
        isinstance(source, dict)
        and bool(source)
        and source == before.get("copied_source")
        and before.get("report")
        == {"path": str(root / "baseline/mutation.xml"), "exists": False},
        "Copied baseline Python hashes match production before any test or mutation",
    )
    xml = _read(
        baseline.get("report"), root, check, "during", "baseline_junit", xml=True
    )
    cases, nodes = _nodes(xml)
    check(
        "during",
        "actual_green_baseline",
        xml is not None and isinstance(baseline.get("result"), dict),
        _result(baseline.get("result"), 0)
        and sorted(nodes) == CATALOG["executed_nodeids"]
        and len(nodes) == len(set(nodes))
        and bool(cases)
        and all(
            not any(c.find(tag) is not None for tag in ("failure", "error", "skipped"))
            for c in cases
        )
        and baseline.get("copied_source") == source,
        "All exact reviewed baseline cases run successfully without changing copied authority",
    )
    baseline_sources = raw.get("baseline_sources")
    sources = {}
    if isinstance(baseline_sources, dict):
        for name in ("history.py", "archive_artwork.py"):
            sources[name] = _source(
                baseline_sources.get(name), root, check, "baseline_" + name
            )
    check(
        "during",
        "baseline_source_matrix",
        isinstance(baseline_sources, dict),
        isinstance(baseline_sources, dict)
        and set(baseline_sources) == {"history.py", "archive_artwork.py"}
        and isinstance(source, dict)
        and all(
            _file(baseline_sources.get(n))
            and baseline_sources[n]["sha256"] == source.get("yt_downloader/" + n)
            for n in sources
        ),
        "Both mutation target files bind to the actual baseline copy",
    )
    mutants = raw.get("mutants")
    typed = (
        isinstance(mutants, list)
        and len(mutants) == 9
        and all(isinstance(m, dict) for m in mutants)
    )
    check(
        "during",
        "exact_mutant_roster",
        typed,
        typed
        and [m.get("id") for m in mutants] == [m["id"] for m in CATALOG["mutants"]],
        "Every reviewed history/artwork mutant has a distinct actual invocation",
    )
    if not typed:
        return
    for i, (m, expected) in enumerate(zip(mutants, CATALOG["mutants"])):
        name = m.get("id", str(i))
        key = "yt_downloader/" + expected["file"]
        text = sources.get(expected["file"])
        old, new = expected["old"], expected["new"]
        timed = _number(m.get("entered_seconds")) and _number(m.get("returned_seconds"))
        check(
            "during",
            name + "_timeline",
            timed,
            timed
            and baseline["elapsed_seconds"]
            < m["entered_seconds"]
            < m["returned_seconds"]
            < after["elapsed_seconds"]
            and (i == 0 or mutants[i - 1]["returned_seconds"] < m["entered_seconds"]),
            "Mutant execution lies between returned baseline and final authority observation",
        )
        expected_after = (
            {
                **(source or {}),
                key: hashlib.sha256(text.replace(old, new, 1).encode()).hexdigest(),
            }
            if isinstance(text, str)
            else {}
        )
        actual_text = _source(m.get("source_file"), root, check, name)
        check(
            "during",
            name + "_single_reviewed_diff",
            all(
                k in m
                for k in (
                    "file",
                    "old",
                    "new",
                    "replacement_count",
                    "source_before",
                    "source_after",
                )
            ),
            isinstance(text, str)
            and text.count(old) == 1
            and m.get("file") == expected["file"]
            and m.get("old") == old
            and m.get("new") == new
            and m.get("replacement_count") == 1
            and m.get("source_before") == source
            and m.get("source_after") == expected_after
            and actual_text == text.replace(old, new, 1),
            "Exactly one reviewed replacement occurs; every other Python source file remains identical",
        )
        xml = _read(m.get("report"), root, check, "during", name + "_junit", xml=True)
        cases, nodes = _nodes(xml)
        check(
            "during",
            name + "_real_assertion_failure",
            xml is not None and isinstance(m.get("result"), dict),
            _result(m.get("result"), 1)
            and sorted(nodes) == CATALOG["executed_nodeids"]
            and len(nodes) == len(set(nodes))
            and any(c.find("failure") is not None for c in cases)
            and not any(
                any(c.find(tag) is not None for tag in ("error", "skipped"))
                for c in cases
            ),
            "Exact reviewed cases execute; an assertion failure kills the mutant, while timeout, import error, skip or missing cases cannot count",
        )
    check(
        "after",
        "canonical_source_preserved",
        all(k in after for k in ("production_source", "baseline_source")),
        after.get("production_source") == source
        and after.get("baseline_source") == source,
        "Canonical production and the green baseline source remain untouched after all nine private mutations",
    )


def evaluate_durability(scenario):
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
                "durability_identity",
                "scenario_id" in raw and "contract" in raw,
                raw.get("scenario_id") == scenario["id"]
                and raw.get("contract") == DURABILITY_CONTRACTS[scenario["id"]],
                "Explicit controlled durability domain and contract match",
            )
            (_activity if "activity" in scenario["id"] else _mutants)(
                raw, Path(scenario["raw_result"]).parent, check
            )
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            check(
                "during",
                "observation_schema",
                False,
                False,
                "Missing or malformed durability observations",
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
        "domain_contract": DURABILITY_CONTRACTS[scenario["id"]],
        "reason": "Optional durable sink episodes or nine private-copy mutation outcomes only; no native or repository-wide acceptance.",
    }
