"""Bounded execution evidence for explicitly reviewed source regression rosters.

The phases here are suite admission, actual per-case outcomes, and unchanged
source authority. They are never product interaction/native UX acceptance.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from .pipeline_interaction import _contained, _number, load_observation
from .transaction_interaction import _file, _trace

CATALOG = json.loads(Path(__file__).with_name("source_suite_catalog.json").read_text())
SOURCE_SUITE_CONTRACTS = {name: "bound-source-regression-suite-v1" for name in CATALOG}


def _read(ref, root, check, phase, name, *, xml=False):
    typed = (
        isinstance(ref, dict)
        and isinstance(ref.get("path"), str)
        and isinstance(ref.get("sha256"), str)
    )
    check(
        phase,
        name + "_owned_path",
        typed,
        typed and _contained(ref["path"], str(root)),
        "Artifact path stays beneath this suite's owned case directory",
    )
    if not typed or not _contained(ref["path"], str(root)):
        return None
    p = Path(ref["path"])
    try:
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("not bounded regular file")
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != ref["sha256"]:
            raise ValueError("content changed")
        obj = ET.fromstring(data) if xml else json.loads(data)
    except (OSError, ValueError, ET.ParseError):
        check(
            phase,
            name + "_content_binding",
            False,
            False,
            "Missing, changed or malformed constituent",
        )
        return None
    check(
        phase,
        name + "_content_binding",
        True,
        True,
        "Original constituent content hash verifies",
    )
    return obj


def _manifest(value):
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("files"), dict)
        or not isinstance(value.get("root"), str)
    ):
        return False
    files = value["files"]
    return (
        "yt_downloader/app.py" in files
        and all(
            isinstance(k, str)
            and k.startswith("yt_downloader/")
            and k.endswith(".py")
            and ".." not in Path(k).parts
            and isinstance(v, str)
            and len(v) == 64
            for k, v in files.items()
        )
        and value.get("sha256")
        == hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        and Path(value["root"]).is_absolute()
    )


def _evaluate(raw, root, specification, check):
    rows = _trace(
        raw, "trace", ["before_suite", "suite_returned", "authority_reobserved"], check
    )
    if rows is None:
        return
    before, during, after = rows
    selectors, minimum, required = [
        raw.get(k) for k in ("selectors", "minimum", "required_nodeids")
    ]
    check(
        "before",
        "reviewed_domain_roster",
        all(k in raw for k in ("selectors", "minimum", "required_nodeids", "scope")),
        selectors == specification["selectors"]
        and minimum == specification["minimum"]
        and required == specification["required_nodeids"]
        and raw.get("scope")
        == "maintained source regression execution; not native or packaged UX",
        "Each domain has an explicit reviewed selector/minimum/required-node roster and source-only scope",
    )
    report = before.get("report")
    check(
        "before",
        "no_prior_report",
        isinstance(report, dict),
        report == {"path": str(root / "cases.xml"), "exists": False},
        "No old JUnit success exists at admission",
    )
    source, probes, assets = [before.get(k) for k in ("source", "probes", "assets")]
    check(
        "before",
        "bound_production_source",
        isinstance(source, dict),
        _manifest(source),
        "Python source inventory has a recomputed content digest and explicit absolute root",
    )
    check(
        "before",
        "bound_domain_probes",
        isinstance(probes, dict),
        isinstance(probes, dict)
        and set(probes) == {s.split("::")[0] for s in specification["selectors"]}
        and all(isinstance(v, str) and len(v) == 64 for v in probes.values()),
        "Every maintained test fixture file in this domain has a recorded hash",
    )
    check(
        "before",
        "bound_scene_assets",
        isinstance(assets, dict),
        isinstance(assets, dict)
        and bool(assets)
        and all(
            k.startswith("yt_downloader/")
            and ".." not in Path(k).parts
            and isinstance(v, str)
            and len(v) == 64
            for k, v in assets.items()
        ),
        "QML, JavaScript, SVG and shader sources used by scene probes are also inventoried",
    )
    command = _read(raw.get("command"), root, check, "during", "command")
    junit = _read(raw.get("junit"), root, check, "during", "junit", xml=True)
    binding = _read(raw.get("binding"), root, check, "after", "binding")
    command_row = during.get("command_result")
    check(
        "during",
        "actual_command_outcome",
        isinstance(command, dict) and isinstance(command_row, dict),
        isinstance(command, dict)
        and command == command_row
        and command.get("returncode") == 0
        and command.get("timed_out") is False
        and command.get("unavailable") is False
        and _number(command.get("duration_seconds"))
        and 0
        < command["duration_seconds"]
        <= during["elapsed_seconds"] - before["elapsed_seconds"] + 1,
        "Actual pytest process returned normally within its observed suite interval; no timeout/tool-absence success",
    )
    argv = command.get("command") if isinstance(command, dict) else None
    typed = (
        isinstance(argv, list)
        and len(argv) >= 8
        and all(isinstance(x, str) for x in argv)
        and isinstance(source, dict)
    )
    check(
        "during",
        "actual_selector_command",
        typed,
        typed
        and argv[1] == "-c"
        and "import yt_downloader.app as app" in argv[2]
        and "is_relative_to(target)" in argv[2]
        and argv[3] == source.get("root")
        and argv[4:]
        == [str(Path(source["root"]) / s) for s in specification["selectors"]]
        + ["--import-mode=importlib", "-q", "--junitxml=" + str(root / "cases.xml")],
        "Bootstrap imports the explicit production tree first and runs exactly this domain's reviewed selectors",
    )
    cases = junit.findall(".//testcase") if junit is not None else []
    nodes = [
        c.get("classname", "").replace(".", "/") + ".py::" + c.get("name", "")
        for c in cases
    ]
    check(
        "during",
        "complete_per_case_outcomes",
        junit is not None,
        bool(cases)
        and len(nodes) == len(set(nodes))
        and sorted(nodes) == specification["executed_nodeids"]
        and len(cases) >= minimum
        and all(
            not any(c.find(tag) is not None for tag in ("skipped", "failure", "error"))
            for c in cases
        ),
        "Every exact enrolled test case executed successfully once; skipped, failing, missing, duplicate or substituted cases cannot qualify",
    )
    for row_name, row in [("returned", during), ("reobserved", after)]:
        f = row.get("report")
        check(
            "during" if row_name == "returned" else "after",
            row_name + "_junit_file",
            isinstance(f, dict),
            _file(f)
            and f.get("path") == str(root / "cases.xml")
            and isinstance(raw.get("junit"), dict)
            and f.get("sha256") == raw["junit"].get("sha256"),
            "Observed generated JUnit file identity matches its bound constituent",
        )
    check(
        "after",
        "unchanged_authority",
        all(k in after for k in ("source", "probes", "assets", "report")),
        _manifest(source)
        and after.get("source") == source
        and after.get("probes") == probes
        and after.get("assets") == assets
        and after.get("report") == during.get("report"),
        "Production Python/scene assets, test fixtures and the result file remain unchanged after execution",
    )
    check(
        "after",
        "binding_agrees_with_observations",
        isinstance(binding, dict),
        isinstance(binding, dict)
        and binding.get("before") == source
        and binding.get("after") == source
        and binding.get("unchanged") is True
        and binding.get("probe_files") == probes
        and binding.get("probe_files_after") == probes
        and binding.get("probes_unchanged") is True
        and binding.get("required_nodeids") == required,
        "Independent source-binding artifact agrees with actual before/after observations",
    )


def evaluate_source_suite(scenario):
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
                "source_suite_identity",
                "scenario_id" in raw and "contract" in raw,
                raw.get("scenario_id") == scenario["id"]
                and raw.get("contract") == SOURCE_SUITE_CONTRACTS[scenario["id"]],
                "Explicit suite domain and source-only contract match",
            )
            _evaluate(
                raw, Path(scenario["raw_result"]).parent, CATALOG[scenario["id"]], check
            )
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            check(
                "during",
                "observation_schema",
                False,
                False,
                "Missing or malformed source suite observations",
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
        "domain_contract": SOURCE_SUITE_CONTRACTS[scenario["id"]],
        "reason": "Suite admission/execution/unchanged-authority evidence only; actual native behavior and usability remain separate.",
    }
