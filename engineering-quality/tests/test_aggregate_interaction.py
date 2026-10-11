"""Known-bad source, partial-suite and diagnostic readback controls."""

import copy
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from quality_harness.aggregate_interaction import AGGREGATE_CONTRACTS, SOURCE_SCOPE
from quality_harness.interaction_coverage import interaction_coverage
from quality_harness.native_ui_checks import QT_SELECTOR_GROUPS
from quality_harness.static_analysis import _pytest_commands

IDS = tuple(AGGREGATE_CONTRACTS)
FIXTURES = Path(__file__).with_name("aggregate_diagnostic_fixtures.json")


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) + "\n")
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def source():
    data = {
        "format": "vodforge-source-files-v1",
        "files": {"yt_downloader/app.py": {"kind": "file", "sha256": "a" * 64}},
    }
    return {
        **data,
        "sha256": hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def junit(path, nodeids):
    suite = ET.Element("testsuite")
    for node in nodeids:
        name, case = node.split("::")
        ET.SubElement(
            suite,
            "testcase",
            classname=name[:-3].replace("/", "."),
            name=case,
            time="0.01",
        )
    path.write_bytes(ET.tostring(suite))
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def build(tmp_path, sid):
    root = tmp_path / "observations"
    root.mkdir()
    repo = tmp_path / "source"
    (repo / "tests").mkdir(parents=True)
    for file in ("test_qt_scene_port.py", "test_qt_component.py"):
        (repo / "tests" / file).write_text("def test_case(): pass\n")
    data = source()
    raw = {
        "scenario_id": sid,
        "contract": AGGREGATE_CONTRACTS[sid],
        "scope": SOURCE_SCOPE,
        "source_root": str(repo),
        "source_before": save(root / "before.json", data),
        "source_after": save(root / "after.json", data),
        "trace": [
            {"phase": "before_suite", "elapsed_seconds": 0.0},
            {"phase": "suite_returned", "elapsed_seconds": 2.0},
            {"phase": "authority_reobserved", "elapsed_seconds": 3.0},
        ],
    }
    if sid.endswith("repository_suite"):
        required = {k: v for k, v, _ in _pytest_commands(repo, "/python")}
        required.update(
            {
                "pytest_harness": [
                    "/python",
                    "-m",
                    "pytest",
                    "-q",
                    "engineering-quality/tests",
                ],
                "compileall": [
                    "/python",
                    "-m",
                    "compileall",
                    "-q",
                    "yt_downloader",
                    "tests",
                ],
                "ruff": [
                    "/python",
                    "-m",
                    "ruff",
                    "check",
                    "yt_downloader",
                    "tests",
                    "--output-format",
                    "json",
                ],
                "ruff_format": [
                    "/python",
                    "-m",
                    "ruff",
                    "format",
                    "--check",
                    "yt_downloader",
                    "tests",
                ],
                "mypy": [
                    "/python",
                    "-m",
                    "mypy",
                    "--ignore-missing-imports",
                    "--follow-imports=skip",
                    "yt_downloader",
                    "tests/typecheck",
                ],
                "bandit": [
                    "/python",
                    "-m",
                    "bandit",
                    "-q",
                    "-r",
                    "yt_downloader",
                    "-f",
                    "json",
                ],
                "vulture": [
                    "/python",
                    "-m",
                    "vulture",
                    "yt_downloader",
                    "--min-confidence",
                    "80",
                ],
                "pip_check": ["/python", "-m", "pip", "check"],
                "pip_audit": [
                    "/python",
                    "-m",
                    "pip_audit",
                    "-r",
                    "requirements.txt",
                    "-f",
                    "json",
                ],
            }
        )
        raw.update(commands={}, logs={}, junit={})
        for name, argv in required.items():
            output = "1 passed in 0.01s\n" if name.startswith("pytest") else ""
            if name.startswith("pytest"):
                argv.append("--junitxml=" + str(root / (name + ".xml")))
                raw["junit"][name] = junit(
                    root / (name + ".xml"), ["tests/test_fixture.py::test_case"]
                )
            raw["commands"][name] = save(
                root / (name + ".json"),
                {
                    "command": argv,
                    "returncode": 0,
                    "timed_out": False,
                    "unavailable": False,
                    "duration_seconds": 0.1,
                    "stdout": output,
                    "stderr": "",
                },
            )
            raw["logs"][name] = {}
            for stream, value in (("stdout", output), ("stderr", "")):
                p = root / (name + "." + stream)
                p.write_text(value)
                raw["logs"][name][stream] = {
                    "path": str(p),
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
    elif sid.endswith("native_surface_contract"):
        raw.update(renderer="qt", native_window_observed=False, groups={})
        for name, files in QT_SELECTOR_GROUPS.items():
            folder = root / name
            folder.mkdir()
            nodes = [file + "::test_fixture" for file in files]
            raw["groups"][name] = {
                "command": save(
                    folder / "command.json",
                    {
                        "command": [
                            "/python",
                            "-m",
                            "pytest",
                            "-p",
                            "quality_harness.native_reports",
                            *files,
                            "-q",
                            "--junitxml=" + str(folder / "native.xml"),
                        ],
                        "returncode": 0,
                        "timed_out": False,
                        "unavailable": False,
                        "duration_seconds": 0.1,
                    },
                ),
                "junit": junit(folder / "native.xml", nodes),
                "collection": save(folder / "collection.json", {"nodeids": nodes}),
                "source_before": save(folder / "before.json", data),
                "source_after": save(folder / "after.json", data),
                "imports": save(
                    folder / "imports.json",
                    {
                        "cwd": str(repo),
                        "imported_modules": {
                            k: str(repo / (k.replace(".", "/") + ".py"))
                            for k in (
                                "yt_downloader.app",
                                "yt_downloader.product_telemetry",
                            )
                        },
                    },
                ),
            }
    else:
        fixture = json.loads(FIXTURES.read_text())
        raw.update(
            {
                key: save(root / (key + ".json"), fixture[key])
                for key in (
                    "source_before",
                    "source_after",
                    "mapping",
                    "delivered",
                    "stored",
                )
            }
        )
    return root, raw


def assess(root, raw):
    ref = save(root / "raw.json", raw)
    return interaction_coverage(
        {
            "id": raw["scenario_id"],
            "evidence_tier": "unit_static",
            "status": "passed",
            "raw_result": ref["path"],
            "raw_result_sha256": ref["sha256"],
        }
    )


@pytest.mark.parametrize("sid", IDS)
def test_explicit_source_domains_qualify_only_bounded_scope(tmp_path, sid):
    root, raw = build(tmp_path, sid)
    result = assess(root, raw)
    assert result["status"] == "passed", result["assertion_mapping"]
    assert result["phase_review"] == dict.fromkeys(
        ("before", "during", "after"), "passed"
    )
    assert result["usability_review"]["status"] == "not_applicable"


@pytest.mark.parametrize("sid", IDS)
@pytest.mark.parametrize(
    "control",
    [
        "missing_trace",
        "reversed_clock",
        "missing_source",
        "changed_source",
        "foreign_scope",
        "foreign_hash",
    ],
)
def test_common_missing_or_contradictory_authority_cannot_pass(tmp_path, sid, control):
    root, raw = build(tmp_path, sid)
    if control == "missing_trace":
        del raw["trace"]
    elif control == "reversed_clock":
        raw["trace"][1]["elapsed_seconds"] = -1
    elif control == "missing_source":
        del raw["source_before"]
    elif control == "changed_source":
        raw["source_after"] = save(root / "changed.json", {})
    elif control == "foreign_scope":
        raw["scope"] = "native interaction and displayed pixels verified"
    elif control == "foreign_hash":
        raw["source_before"]["sha256"] = "0" * 64
    assert assess(root, raw)["status"] != "passed"


@pytest.mark.parametrize(
    "control",
    [
        "missing_tool",
        "timeout",
        "failed",
        "subset",
        "changed_log",
        "junit_skip",
        "junit_failure",
        "count_mismatch",
    ],
)
def test_static_suite_refuses_partial_execution(tmp_path, control):
    root, raw = build(tmp_path, IDS[0])
    name = "pytest"
    if control == "missing_tool":
        del raw["commands"]["pip_audit"]
    elif control in {"timeout", "failed", "subset", "count_mismatch"}:
        data = json.loads(Path(raw["commands"][name]["path"]).read_text())
        if control == "timeout":
            data["timed_out"] = True
        elif control == "failed":
            data["returncode"] = 1
        elif control == "subset":
            data["command"][4] = "tests/test_only_one.py"
        else:
            data["stdout"] = "2 passed in 0.1s"
        raw["commands"][name] = save(root / "bad-command.json", data)
    elif control == "changed_log":
        Path(raw["logs"][name]["stdout"]["path"]).write_text("substituted")
    else:
        tree = ET.parse(raw["junit"][name]["path"]).getroot()
        ET.SubElement(
            tree.find("testcase"), "skipped" if control == "junit_skip" else "failure"
        )
        p = root / "bad.xml"
        p.write_bytes(ET.tostring(tree))
        raw["junit"][name] = {
            "path": str(p),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
    assert assess(root, raw)["status"] != "passed"


@pytest.mark.parametrize(
    "control",
    [
        "missing_group",
        "wrong_renderer",
        "native_claim",
        "foreign_import",
        "missing_case",
        "extra_case",
        "changed_group_source",
        "crash",
    ],
)
def test_offscreen_group_does_not_hide_incomplete_or_foreign_execution(
    tmp_path, control
):
    root, raw = build(tmp_path, IDS[1])
    group = raw["groups"]["components"]
    if control == "missing_group":
        del raw["groups"]["scene"]
    elif control == "wrong_renderer":
        raw["renderer"] = "tk"
    elif control == "native_claim":
        raw["native_window_observed"] = True
    elif control == "changed_group_source":
        group["source_before"] = save(root / "components" / "bad-source.json", {})
    else:
        key = (
            "imports"
            if control == "foreign_import"
            else "command"
            if control == "crash"
            else "collection"
        )
        data = json.loads(Path(group[key]["path"]).read_text())
        if control == "foreign_import":
            data["imported_modules"]["yt_downloader.app"] = "/foreign/app.py"
        elif control == "crash":
            data["returncode"] = 139
        elif control == "missing_case":
            data["nodeids"].pop()
        else:
            data["nodeids"].append("tests/test_foreign.py::test_other")
        group[key] = save(root / "components" / "bad.json", data)
    assert assess(root, raw)["status"] != "passed"


@pytest.mark.parametrize(
    "control",
    [
        "missing_producer",
        "extra_producer",
        "lost_row",
        "duplicate_row",
        "changed_dimension",
        "lost_failure",
        "operation_identity",
        "wrong_case_order",
    ],
)
def test_diagnostic_transport_success_does_not_hide_bad_outcome(tmp_path, control):
    root, raw = build(tmp_path, IDS[2])
    key = (
        "mapping"
        if control in {"missing_producer", "extra_producer", "wrong_case_order"}
        else "stored"
    )
    data = json.loads(Path(raw[key]["path"]).read_text())
    if control == "missing_producer":
        data.pop()
    elif control == "extra_producer":
        data.append(copy.deepcopy(data[0]))
    elif control == "lost_row":
        data.pop()
    elif control == "duplicate_row":
        data.append(copy.deepcopy(data[0]))
    elif control == "changed_dimension":
        data[0]["dimensions"] = "{}"
    elif control == "lost_failure":
        next(r for r in data if r.get("failure_detail"))["failure_detail"] = None
    elif control == "operation_identity":
        row = next(r for r in data if "operation_id" in r["dimensions"])
        dims = json.loads(row["dimensions"])
        dims["operation_id"] = "foreign"
        row["dimensions"] = json.dumps(dims)
    else:
        data[0]["event_ids"].reverse()
    raw[key] = save(root / "bad.json", data)
    assert assess(root, raw)["status"] != "passed"


@pytest.mark.parametrize(
    "control", [None, "unexpected", "all_skipped", "summary_mismatch"]
)
def test_source_only_exclusions_remain_explicit_and_do_not_prove_execution(
    tmp_path, control
):
    root, raw = build(tmp_path, IDS[0])
    name = "pytest"
    tree = ET.parse(raw["junit"][name]["path"]).getroot()
    second = ET.SubElement(
        tree, "testcase", classname="tests.test_windows", name="test_native", time="0.0"
    )
    ET.SubElement(
        second,
        "skipped",
        message="native display required"
        if control != "unexpected"
        else "unexpected setup failure",
    )
    if control == "all_skipped":
        ET.SubElement(
            tree.find("testcase"), "skipped", message="native display required"
        )
    path = root / "scoped.xml"
    path.write_bytes(ET.tostring(tree))
    raw["junit"][name] = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    command = json.loads(Path(raw["commands"][name]["path"]).read_text())
    command["stdout"] = (
        "0 passed, 2 skipped in 0.1s"
        if control == "all_skipped"
        else "1 passed, 1 skipped in 0.1s"
    )
    if control == "summary_mismatch":
        command["stdout"] = "1 passed in 0.1s"
    raw["commands"][name] = save(root / "scoped-command.json", command)
    log = root / "scoped.stdout.log"
    log.write_text(command["stdout"])
    raw["logs"][name]["stdout"] = {
        "path": str(log),
        "sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
    }
    result = assess(root, raw)
    assert (result["status"] == "passed") is (control is None)
    assert result["usability_review"]["status"] == "not_applicable"


def test_command_durations_cannot_fit_in_fabricated_instantaneous_phase(tmp_path):
    root, raw = build(tmp_path, IDS[0])
    raw["trace"][1]["elapsed_seconds"] = 0.000001
    raw["trace"][2]["elapsed_seconds"] = 0.000002
    assert assess(root, raw)["status"] != "passed"
