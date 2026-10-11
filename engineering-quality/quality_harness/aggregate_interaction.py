"""Independent bounded source-suite, offscreen and local-D1 assertions.

Suite phases describe admission, actual process/case results and source stability.
They do not substitute for native pointer, playback or packaged usability evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .pipeline_interaction import _number, load_observation
from .source_identity import validate_manifest
from .source_suite_interaction import _read
from .transaction_interaction import _trace

AGGREGATE_CONTRACTS = {
    "unit_static.repository_suite": "bounded-repository-suite-v1",
    "unit_static.native_surface_contract": "bounded-offscreen-qt-suite-v1",
    "unit_static.telemetry_presentation_contract": "bounded-local-diagnostic-matrix-v1",
}
SOURCE_SCOPE = (
    "source admission, execution and stable authority; no native or packaged UX"
)


def _source(value):
    return isinstance(value, dict) and validate_manifest(value, value.get("sha256"))


def _snapshot(value):
    if not isinstance(value, dict) or set(value) != {"desktop", "backend"}:
        return False
    for entry in value.values():
        files = entry.get("files", {})
        if not files or not Path(entry.get("root", "")).is_absolute():
            return False
        if any(
            Path(k).is_absolute()
            or ".." in Path(k).parts
            or not re.fullmatch("[0-9a-f]{64}", str(v))
            for k, v in files.items()
        ):
            return False
        if (
            entry.get("manifest_sha256")
            != hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        ):
            return False
    return True


def _returned(command):
    return (
        isinstance(command, dict)
        and type(command.get("returncode")) is int
        and command["returncode"] == 0
        and command.get("timed_out") is False
        and command.get("unavailable") is False
        and _number(command.get("duration_seconds"))
        and command["duration_seconds"] > 0
        and isinstance(command.get("command"), list)
        and bool(command["command"])
    )


# These are explicit source-suite exclusions. They prove no native interaction,
# OS primitive or hardware behavior; separately required native gates stay strict.
SOURCE_ONLY_SKIP_REASONS = {
    "native display required",
    "Native display required",
    "explicit native run required",
    "requires native Tcl/Tk",
    "native Tk",
    "Mac native display required",
    "explicit native display required",
    "Interactive Windows native display required",
    "AppKit overlay owner",
    "Native Tk display required",
    "Interactive Mac native display required",
    "Native Mac idle queue required",
    "macOS native pointer",
    "native GUI lease",
    "explicit Mac native display and OS input required",
    "explicit Mac native window and OS input required",
    "Requires explicitly enabled Mac native file QA",
    "Mac native resource evidence required",
    "macOS Core Graphics bridge",
    "explicit real-provider native run required",
    "explicit Mac native scale measurement required",
    "explicit Mac source-native real-provider run required",
    "native Mac presentation required",
    "Explicit Windows native display required",
    "requires an isolated native macOS Qt run",
    "explicit Mac native display required",
    "requires explicit Mac native controls and OS keyboard",
    "explicit real-provider native queue run required",
    "native GUI lease required",
    "actual Mac native display required",
    "Mac native surface rendering required",
    "Mac source-native OS-injected interaction required",
    "real Windows window required",
    "real Windows process required",
    "Win32 window API",
    "requires actual Windows job kernel",
    "requires an explicitly enabled NVIDIA hardware run",
    "requires Windows Forms",
    "PowerShell is required for the native Windows visibility gate",
    "requires PowerShell runtime",
    "requires macOS file tools",
    "macOS color reference bridge",
}


def _cases(junit, *, source_only=False):
    cases = junit.findall(".//testcase") if junit is not None else []
    nodes = [
        c.get("classname", "").replace(".", "/") + ".py::" + c.get("name", "")
        for c in cases
    ]
    return nodes, bool(cases) and any(c.find("skipped") is None for c in cases) and len(
        nodes
    ) == len(set(nodes)) and all(
        not any(c.find(tag) is not None for tag in ("failure", "error"))
        and (
            c.find("skipped") is None
            or (
                source_only
                and c.find("skipped").get("message") in SOURCE_ONLY_SKIP_REASONS
            )
        )
        and _number(float(c.get("time", "nan")))
        and float(c.get("time", "-1")) >= 0
        for c in cases
    )


def _repository(raw, root, check):
    from .release_gate import FAST_REQUIRED_COMMANDS
    from .static_analysis import _pytest_commands

    commands = raw.get("commands", {})
    check(
        "during",
        "required_command_inventory",
        isinstance(commands, dict),
        set(FAST_REQUIRED_COMMANDS) <= set(commands),
        "All twelve release-required commands have separate bound process results",
    )
    durations = []
    for name in FAST_REQUIRED_COMMANDS:
        entry = _read(commands.get(name), root, check, "during", name + "_timing")
        if _returned(entry):
            durations.append(entry["duration_seconds"])
    trace = raw.get("trace", [])
    elapsed = trace[1].get("elapsed_seconds") if len(trace) >= 2 else None
    check(
        "during",
        "processes_within_observed_interval",
        _number(elapsed),
        _number(elapsed)
        and len(durations) == len(FAST_REQUIRED_COMMANDS)
        and sum(durations) <= elapsed + 0.01,
        "All sequential required command durations fit within the captured execution interval",
    )
    for name in FAST_REQUIRED_COMMANDS:
        command = _read(commands.get(name), root, check, "during", name)
        check(
            "during",
            name + "_returned",
            command is not None,
            _returned(command),
            "Recorded process returned normally; no timeout or unavailable success",
        )
        if not isinstance(command, dict):
            continue
        argv = command.get("command", [])
        if name in {"pytest", "pytest_qt_components", "pytest_qt_scene"}:
            source_root = Path(raw.get("source_root", ""))
            expected = {
                k: v for k, v, _deadline in _pytest_commands(source_root, argv[0])
            }[name]
            # The sole extra option records cases; it does not select or skip tests.
            check(
                "during",
                name + "_complete_invocation",
                bool(argv),
                argv == expected + ["--junitxml=" + str(root / (name + ".xml"))],
                "Full maintained test-group invocation, including every Qt exclusion/selector",
            )
        else:
            arguments = {
                "pytest_harness": [
                    "-m",
                    "pytest",
                    "-q",
                    "engineering-quality/tests",
                    "--junitxml=" + str(root / "pytest_harness.xml"),
                ],
                "compileall": ["-m", "compileall", "-q", "yt_downloader", "tests"],
                "ruff": [
                    "-m",
                    "ruff",
                    "check",
                    "yt_downloader",
                    "tests",
                    "--output-format",
                    "json",
                ],
                "ruff_format": [
                    "-m",
                    "ruff",
                    "format",
                    "--check",
                    "yt_downloader",
                    "tests",
                ],
                "mypy": [
                    "-m",
                    "mypy",
                    "--ignore-missing-imports",
                    "--follow-imports=skip",
                    "yt_downloader",
                    "tests/typecheck",
                ],
                "bandit": ["-m", "bandit", "-q", "-r", "yt_downloader", "-f", "json"],
                "vulture": ["-m", "vulture", "yt_downloader", "--min-confidence", "80"],
                "pip_check": ["-m", "pip", "check"],
                "pip_audit": [
                    "-m",
                    "pip_audit",
                    "-r",
                    "requirements.txt",
                    "-f",
                    "json",
                ],
            }
            check(
                "during",
                name + "_invocation",
                bool(argv),
                argv[1:] == arguments[name],
                "Exact maintained static/tool invocation; no selected subset or substituted argument",
            )
        for stream in ("stdout", "stderr"):
            ref = raw.get("logs", {}).get(name, {}).get(stream)
            try:
                path = Path(ref["path"])
                data = path.read_bytes()
                valid = (
                    path.is_relative_to(root)
                    and not path.is_symlink()
                    and hashlib.sha256(data).hexdigest() == ref["sha256"]
                    and data.decode() == command.get(stream)
                )
            except (KeyError, TypeError, OSError, UnicodeError):
                valid = False
            check(
                "after",
                name + "_" + stream + "_bound",
                ref is not None,
                valid,
                "Unchanged original output bytes agree with the command record",
            )
        if name.startswith("pytest"):
            junit = _read(
                raw.get("junit", {}).get(name),
                root,
                check,
                "during",
                name + "_junit",
                xml=True,
            )
            _nodes, valid = _cases(junit, source_only=True)
            check(
                "during",
                name + "_case_results",
                junit is not None,
                valid,
                "Every collected case is recorded; executed cases pass, and explicit source-only exclusions prove no native behavior",
            )
            totals = re.findall(
                r"(?<![0-9])([0-9]+) passed(?:[ ,]|$)", str(command.get("stdout"))
            )
            check(
                "during",
                name + "_case_count",
                bool(totals),
                bool(totals)
                and int(totals[-1])
                == sum(c.find("skipped") is None for c in junit.findall(".//testcase"))
                and sum(
                    c.find("skipped") is not None for c in junit.findall(".//testcase")
                )
                == (
                    int(
                        re.findall(
                            r"(?<![0-9])([0-9]+) skipped(?:[ ,]|$)",
                            str(command.get("stdout")),
                        )[-1]
                    )
                    if " skipped" in str(command.get("stdout"))
                    else 0
                ),
                "Independent JUnit count agrees with actual pytest output",
            )


def _native(raw, root, check):
    from .native_ui_checks import QT_SELECTOR_GROUPS

    groups = raw.get("groups", {})
    check(
        "before",
        "reviewed_qt_scope",
        "renderer" in raw,
        raw.get("renderer") == "qt" and raw.get("native_window_observed") is False,
        "Qt offscreen component scope is explicit; no displayed native window claim",
    )
    check(
        "during",
        "required_groups",
        isinstance(groups, dict),
        set(groups) == set(QT_SELECTOR_GROUPS),
        "Scene, components and reported regressions are all present",
    )
    for name, selectors in QT_SELECTOR_GROUPS.items():
        refs = groups.get(name, {})
        group = root / name
        command = _read(refs.get("command"), group, check, "during", name + "_command")
        junit = _read(
            refs.get("junit"), group, check, "during", name + "_junit", xml=True
        )
        collected = _read(
            refs.get("collection"), group, check, "before", name + "_collection"
        )
        before = _read(
            refs.get("source_before"), group, check, "before", name + "_source_before"
        )
        after = _read(
            refs.get("source_after"), group, check, "after", name + "_source_after"
        )
        imports = _read(refs.get("imports"), group, check, "before", name + "_imports")
        check(
            "after",
            name + "_stable_source",
            before is not None and after is not None,
            _source(before)
            and before == after
            and before == raw.get("observed_source"),
            "Complete source manifests recompute and remain equal",
        )
        check(
            "during",
            name + "_normal_return",
            command is not None,
            _returned(command),
            "Separate process returned normally",
        )
        argv = command.get("command", []) if isinstance(command, dict) else []
        check(
            "during",
            name + "_selectors",
            bool(argv),
            argv[1:]
            == [
                "-m",
                "pytest",
                "-p",
                "quality_harness.native_reports",
                *selectors,
                "-q",
                "--junitxml=" + str(group / "native.xml"),
            ],
            "All maintained group selectors execute; no selected-case omission",
        )
        nodes, valid = _cases(junit)
        roster = collected.get("nodeids") if isinstance(collected, dict) else None
        check(
            "during",
            name + "_per_case_outcomes",
            junit is not None and roster is not None,
            valid
            and sorted(nodes) == sorted(roster)
            and len(roster) == len(set(roster))
            and {n.split("::")[0] for n in roster} == set(selectors),
            "Every collected case in every required file has a successful final outcome",
        )
        source_root = raw.get("source_root")
        modules = (
            imports.get("imported_modules", {}) if isinstance(imports, dict) else {}
        )
        check(
            "before",
            name + "_import_authority",
            imports is not None,
            isinstance(imports, dict)
            and isinstance(source_root, str)
            and imports.get("cwd") == source_root
            and all(
                Path(modules.get(k, "/foreign")).is_relative_to(Path(source_root))
                for k in ("yt_downloader.app", "yt_downloader.product_telemetry")
            ),
            "Actual imported production modules belong to the observed source tree",
        )


def _presentation(raw, root, check):
    from .diagnostic_expectations import verify_scenario_events
    from .qt_diagnostic_probes import QT_COVERAGE_CASES, QT_PRESENTATION_CASES

    expected = {*QT_PRESENTATION_CASES, *QT_COVERAGE_CASES}
    mapping = _read(raw.get("mapping"), root, check, "during", "producer_mapping")
    delivered = _read(raw.get("delivered"), root, check, "during", "delivered_payloads")
    stored = _read(raw.get("stored"), root, check, "after", "local_d1_readback")
    check(
        "during",
        "complete_producer_roster",
        isinstance(mapping, list),
        isinstance(mapping, list)
        and len(mapping) == len(expected)
        and {r.get("case") for r in mapping} == expected,
        "All twelve explicit Qt producers, including timeout/failure cases",
    )
    by_id = {r.get("event_id"): r for r in stored} if isinstance(stored, list) else {}
    payloads = (
        {r.get("event_id"): r for r in delivered} if isinstance(delivered, list) else {}
    )
    check(
        "after",
        "exact_delivery_set",
        isinstance(stored, list) and isinstance(delivered, list),
        bool(by_id)
        and len(by_id) == len(stored) == len(delivered) == len(payloads)
        and set(by_id) == set(payloads),
        "No lost, duplicate or extra accepted D1 row",
    )
    if (
        not isinstance(mapping, list)
        or not isinstance(stored, list)
        or not isinstance(delivered, list)
    ):
        return
    for key, row in by_id.items():
        payload = payloads.get(key, {})
        normalized = dict(row)
        for field in ("dimensions", "failure_detail"):
            value = normalized.get(field)
            if isinstance(value, str):
                normalized[field] = json.loads(value)
        expected_payload = dict(payload)
        if isinstance(payload.get("occurred_at"), str):
            expected_payload["occurred_at"] = (
                datetime.fromisoformat(payload["occurred_at"].replace("Z", "+00:00"))
                .astimezone(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
        valid = all(
            normalized.get(field) == expected_payload.get(field) for field in row
        )
        check(
            "after",
            "payload_" + str(key),
            True,
            valid,
            "Every persisted field agrees with its producer payload, including failure diagnostics",
        )
    mapped = []
    for item in mapping:
        ids = item.get("event_ids", [])
        actual = []
        valid = (
            bool(ids)
            and len(ids) == len(set(ids))
            and all(k in by_id for k in ids)
            and ids == [r["event_id"] for r in delivered if r["event_id"] in ids]
        )
        if valid:
            for key in ids:
                event = dict(by_id[key])
                for field in ("dimensions", "failure_detail"):
                    if isinstance(event.get(field), str):
                        event[field] = json.loads(event[field])
                actual.append(event)
            try:
                verify_scenario_events(item["case"], actual)
            except (AssertionError, KeyError, TypeError, ValueError):
                valid = False
        check(
            "after",
            str(item.get("case")) + "_diagnostic_outcome",
            bool(ids),
            valid,
            "Independent producer-specific ordered outcome and operation identity assertions over actual D1 rows",
        )
        mapped.extend(ids)
    check(
        "after",
        "every_row_accounted",
        True,
        len(mapped) == len(set(mapped)) and set(mapped) == set(by_id),
        "No unassigned or multiply assigned producer event",
    )


def evaluate_aggregate(scenario):
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
            sid = scenario["id"]
            check(
                "before",
                "explicit_domain_scope",
                "contract" in raw and "scope" in raw,
                raw.get("scenario_id") == sid
                and raw.get("contract") == AGGREGATE_CONTRACTS[sid]
                and raw.get("scope") == SOURCE_SCOPE,
                "Only the explicit reviewed source/offscreen/local-D1 domain is enrolled",
            )
            phases = _trace(
                raw,
                "trace",
                ["before_suite", "suite_returned", "authority_reobserved"],
                check,
            )
            root = Path(scenario["raw_result"]).parent
            if phases is not None:
                before = _read(
                    raw.get("source_before"), root, check, "before", "source_before"
                )
                after = _read(
                    raw.get("source_after"), root, check, "after", "source_after"
                )
                valid = (
                    _snapshot(before)
                    if sid.endswith("telemetry_presentation_contract")
                    else _source(before)
                )
                check(
                    "after",
                    "stable_complete_authority",
                    before is not None and after is not None,
                    valid and before == after,
                    "Source admission and final authority are separate, hash-bound original observations",
                )
                raw["observed_source"] = before
                {
                    "unit_static.repository_suite": _repository,
                    "unit_static.native_surface_contract": _native,
                    "unit_static.telemetry_presentation_contract": _presentation,
                }[sid](raw, root, check)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError, OSError):
            check(
                "during",
                "observation_schema",
                False,
                False,
                "Missing or malformed constituent; no success inferred",
            )
    phases = {}
    for phase in ("before", "during", "after"):
        states = [a["status"] for a in assertions if a["phase"] == phase]
        phases[phase] = (
            "failed"
            if "failed" in states
            else "unproven"
            if not states or "unproven" in states
            else "passed"
        )
    status = (
        "failed"
        if "failed" in phases.values()
        else "unproven"
        if "unproven" in phases.values()
        else "passed"
    )
    return {
        "status": status,
        "scenario_id": scenario["id"],
        "required_phases": list(phases),
        "phase_review": phases,
        "assertion_mapping": assertions,
        "domain_contract": AGGREGATE_CONTRACTS[scenario["id"]],
        "reason": SOURCE_SCOPE,
    }
