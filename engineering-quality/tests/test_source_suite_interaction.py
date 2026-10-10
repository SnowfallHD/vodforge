"""Explicit per-domain source-suite rosters and constituent bindings fail closed."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from quality_harness.interaction_coverage import interaction_coverage
from quality_harness.observation_fixtures import relocate_observation

FIXTURES = json.loads(
    Path(__file__).with_name("source_suite_observations.json").read_text()
)
CONTROLS = [
    "foreign_identity",
    "foreign_contract",
    "foreign_scope",
    "missing_trace",
    "reversed_trace",
    "missing_clock",
    "foreign_raw_hash",
    "wrong_selectors",
    "wrong_minimum",
    "wrong_required",
    "prior_report",
    "missing_source",
    "wrong_source_digest",
    "missing_probe",
    "missing_asset",
    "changed_source",
    "changed_probe",
    "changed_asset",
    "changed_after_report",
    "escaped_junit",
    "missing_junit_hash",
    "changed_command_return",
    "changed_command_timeout",
    "changed_command_unavailable",
    "changed_bootstrap",
    "changed_target",
    "changed_selector_command",
    "changed_actual_return",
    "changed_duration",
    "xml_failure",
    "xml_error",
    "xml_skipped",
    "xml_missing_case",
    "xml_duplicate_case",
    "xml_substitution",
    "binding_source_changed",
    "binding_probe_changed",
    "binding_required_changed",
    "binding_false_unchanged",
]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, a):
    p.write_text(json.dumps(a, indent=2) + "\n")
    return {"path": str(p), "sha256": sha(p)}


def mutate(a, name, folder):
    before, during, after = a.get("trace", [{}, {}, {}])
    if name == "foreign_identity":
        a["scenario_id"] = "other"
    elif name == "foreign_contract":
        a["contract"] = "other"
    elif name == "foreign_scope":
        a["scope"] = "native UX certified"
    elif name == "missing_trace":
        del a["trace"]
    elif name == "reversed_trace":
        a["trace"].reverse()
    elif name == "missing_clock":
        del a["trace"][0]["elapsed_seconds"]
    elif name == "foreign_raw_hash":
        pass
    elif name == "wrong_selectors":
        a["selectors"] = ["tests/other.py"]
    elif name == "wrong_minimum":
        a["minimum"] = 0
    elif name == "wrong_required":
        a["required_nodeids"] = ["other"]
    elif name == "prior_report":
        before["report"]["exists"] = True
    elif name == "missing_source":
        del before["source"]["files"]["yt_downloader/app.py"]
    elif name == "wrong_source_digest":
        before["source"]["sha256"] = "0" * 64
    elif name == "missing_probe":
        before["probes"].pop(next(iter(before["probes"])))
    elif name == "missing_asset":
        before["assets"] = {}
    elif name == "changed_source":
        after["source"]["sha256"] = "0" * 64
    elif name == "changed_probe":
        after["probes"][next(iter(after["probes"]))] = "0" * 64
    elif name == "changed_asset":
        after["assets"][next(iter(after["assets"]))] = "0" * 64
    elif name == "changed_after_report":
        after["report"]["sha256"] = "0" * 64
    elif name == "escaped_junit":
        a["junit"]["path"] = "/foreign/cases.xml"
    elif name == "missing_junit_hash":
        del a["junit"]["sha256"]
    elif name == "changed_actual_return":
        during["command_result"]["returncode"] = 1
    elif name == "changed_duration":
        during["command_result"]["duration_seconds"] = 10000
    elif name.startswith("changed_command_") or name in {
        "changed_bootstrap",
        "changed_target",
        "changed_selector_command",
    }:
        command = json.loads(Path(a["command"]["path"]).read_text())
        if name == "changed_command_return":
            command["returncode"] = 1
        elif name == "changed_command_timeout":
            command["timed_out"] = True
        elif name == "changed_command_unavailable":
            command["unavailable"] = True
        elif name == "changed_bootstrap":
            command["command"][2] = "import pytest; pytest.main()"
        elif name == "changed_target":
            command["command"][3] = "/foreign/source"
        elif name == "changed_selector_command":
            command["command"][4] = "/foreign/test.py"
        a["command"] = save(folder / ("constituent-" + name + ".json"), command)
        during["command_result"] = command
    elif name.startswith("xml_"):
        tree = ET.fromstring(Path(a["junit"]["path"]).read_text())
        cases = tree.findall(".//testcase")
        case = cases[0]
        if name in {"xml_failure", "xml_error", "xml_skipped"}:
            ET.SubElement(case, name.split("_")[1])
        elif name == "xml_substitution":
            case.set("name", "unreviewed_replacement")
        elif name == "xml_missing_case":
            for parent in tree.iter():
                if case in list(parent):
                    parent.remove(case)
                    break
        elif name == "xml_duplicate_case":
            for parent in tree.iter():
                if case in list(parent):
                    parent.append(ET.fromstring(ET.tostring(case)))
                    break
        p = folder / ("constituent-" + name + ".xml")
        p.write_bytes(ET.tostring(tree))
        a["junit"] = {"path": str(p), "sha256": sha(p)}
        # Preserve the observation's original path: altered JUnit contents must
        # be rejected by exact per-case outcomes, not just a path disagreement.
        for row in (during, after):
            row["report"].update(sha256=sha(p), size_bytes=p.stat().st_size)
    elif name.startswith("binding_"):
        binding = json.loads(Path(a["binding"]["path"]).read_text())
        if name == "binding_source_changed":
            binding["after"]["sha256"] = "0" * 64
        elif name == "binding_probe_changed":
            binding["probe_files_after"][next(iter(binding["probe_files_after"]))] = (
                "0" * 64
            )
        elif name == "binding_required_changed":
            binding["required_nodeids"] = ["other"]
        elif name == "binding_false_unchanged":
            binding["unchanged"] = False
        a["binding"] = save(folder / ("constituent-" + name + ".json"), binding)


def materialize(tmp_path, example):
    folder = tmp_path / example["folder"]
    folder.mkdir()
    a = relocate_observation(example["raw"], example["old_root"], folder)
    source_root = a["trace"][0]["source"]["root"]
    native_source = Path(source_root).resolve()
    a = relocate_observation(a, source_root, native_source)
    for key in ("command", "binding", "junit"):
        value = example["constituents"][key]
        p = (
            folder
            / (
                {
                    "command": "command.json",
                    "binding": "source-binding.json",
                    "junit": "cases.xml",
                }[key]
            )
        )
        if key == "junit":
            p.write_text(
                value.replace(example["old_root"], str(folder)), encoding="utf-8"
            )
        else:
            value = relocate_observation(value, example["old_root"], folder)
            value = relocate_observation(value, source_root, native_source)
            if key == "command":
                command_root = a["trace"][0]["source"]["root"]
                count = len(a["selectors"])
                value["command"][4 : 4 + count] = [
                    str(Path(command_root) / selector) for selector in a["selectors"]
                ]
            p.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        a[key] = {"path": str(p), "sha256": sha(p)}
        if key == "command":
            a["trace"][1]["command_result"] = json.loads(p.read_text())
        if key == "junit":
            for row in a["trace"][1:]:
                row["report"].update(sha256=sha(p), size_bytes=p.stat().st_size)
    ref = save(folder / "observation.json", a)
    return (
        dict(
            example["scenario"], raw_result=ref["path"], raw_result_sha256=ref["sha256"]
        ),
        a,
        folder,
    )


@pytest.mark.parametrize("i", range(len(FIXTURES)))
def test_source_suite_actual_shape_qualifies(tmp_path, i):
    s, _, _ = materialize(tmp_path, FIXTURES[i])
    q = interaction_coverage(s)
    assert q["status"] == "passed", q
    assert q["usability_review"]["status"] == "not_applicable"


@pytest.mark.parametrize(
    "i,name", [(i, n) for i in range(len(FIXTURES)) for n in CONTROLS]
)
def test_altered_source_suite_cannot_qualify(tmp_path, i, name):
    s, a, folder = materialize(tmp_path, FIXTURES[i])
    mutate(a, name, folder)
    ref = save(folder / "mutation.json", a)
    s.update(
        raw_result=ref["path"],
        raw_result_sha256="0" * 64 if name == "foreign_raw_hash" else ref["sha256"],
    )
    q = interaction_coverage(s)
    assert q["status"] in {"failed", "unproven"}, q
