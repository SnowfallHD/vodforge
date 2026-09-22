import json

import pytest
from quality_harness import recovery_contract
from quality_harness.recovery_contract import (
    REQUIRED_SCENARIOS,
    complete_report,
    recovery_class_contract,
)
from quality_harness.release_gate import NORMAL_REQUIRED_SCENARIOS
from quality_harness.util import CommandResult


@pytest.mark.parametrize(
    ("body", "minimum", "passed"),
    [
        ("", 1, False),
        ("<testcase/>", 2, False),
        ("<testcase><skipped/></testcase>", 1, False),
        ("<testcase><failure/></testcase>", 1, False),
        ("<testcase><error/></testcase>", 1, False),
        ("<testcase/><testcase/>", 2, True),
    ],
)
def test_regression_class_cannot_pass_with_missing_skipped_or_reduced_cases(
    tmp_path, body, minimum, passed
):
    path = tmp_path / "cases.xml"
    path.write_text("<testsuite>" + body + "</testsuite>")
    assert complete_report(path, minimum)[0] is passed


@pytest.mark.parametrize(
    "failure", ["timeout", "missing", "changed_source", "changed_probes"]
)
def test_class_runner_rejects_stale_success_and_records_exact_source(
    tmp_path, monkeypatch, failure
):
    source = tmp_path / "source"
    (source / "yt_downloader").mkdir(parents=True)
    production = source / "yt_downloader/app.py"
    production.write_text("# exact candidate\n")
    (source / "tests").mkdir()
    (source / "tests/test_library_recovery_regressions.py").write_text(
        "# maintained probes\n"
    )
    output = tmp_path / "evidence"
    output.mkdir()
    report = output / "cases.xml"
    report.write_text("<testsuite>" + "<testcase/>" * 3 + "</testsuite>")

    def execute(command, **kwargs):
        assert not report.exists()
        assert kwargs["env"]["VODFORGE_NATIVE_UI_TESTS"] == "0"
        assert kwargs["env"]["HOME"] == str(output / "isolated-home")
        assert str(source) in command
        if failure in {"changed_source", "changed_probes"}:
            report.write_text("<testsuite>" + "<testcase/>" * 3 + "</testsuite>")
            if failure == "changed_source":
                production.write_text("# changed during validation\n")
            else:
                (source / "tests/test_library_recovery_regressions.py").write_text(
                    "# probes changed during validation\n"
                )
        return CommandResult(
            command,
            None if failure == "timeout" else 0,
            0.1,
            "captured stdout",
            "captured stderr",
            timed_out=failure == "timeout",
        )

    monkeypatch.setattr(recovery_contract, "run_command", execute)
    scenario, _ = recovery_class_contract(source, output, "canonical_facts")
    assert scenario["status"] == "failed"
    binding = json.loads((output / "source-binding.json").read_text())
    assert binding["before"]["root"] == str(source)
    assert binding["unchanged"] is (failure != "changed_source")
    assert binding["probes_unchanged"] is (failure != "changed_probes")
    command = json.loads((output / "command.json").read_text())
    assert command["stdout"] == "captured stdout"


def test_every_recovery_regression_class_is_required_for_normal_release():
    assert REQUIRED_SCENARIOS == {
        "unit_static.recovery_canonical_facts",
        "unit_static.recovery_selected_item",
        "unit_static.recovery_retired_presets",
        "unit_static.recovery_bounded_expansion",
        "unit_static.recovery_draft_coherence",
        "unit_static.recovery_durable_roundtrip",
    }
    assert REQUIRED_SCENARIOS <= NORMAL_REQUIRED_SCENARIOS


def test_unrelated_passing_cases_cannot_replace_required_semantic_probe(tmp_path):
    report = tmp_path / "cases.xml"
    unrelated = '<testcase classname="tests.test_other" name="test_required"/>'
    report.write_text("<testsuite>" + unrelated * 100 + "</testsuite>")
    required = ("tests/test_projection.py::test_required",)
    assert complete_report(report, 1, required) == (False, 100)
    report.write_text(
        '<testsuite><testcase classname="tests.test_projection" name="test_required[one]"/></testsuite>'
    )
    assert complete_report(report, 1, required) == (True, 1)


def test_source_binding_is_identical_for_native_and_windows_path_spelling(tmp_path):
    from pathlib import PureWindowsPath
    from types import SimpleNamespace

    (tmp_path / "yt_downloader").mkdir()
    actual = tmp_path / "yt_downloader/app.py"
    actual.write_text("# exact same source bytes\n")
    expected = recovery_contract.source_binding(tmp_path)

    class WindowsSpelling:
        def __truediv__(self, _name):
            file = SimpleNamespace(
                relative_to=lambda _root: PureWindowsPath("yt_downloader/app.py"),
                read_bytes=actual.read_bytes,
            )
            return SimpleNamespace(rglob=lambda _pattern: [file])

        def resolve(self):
            return tmp_path.resolve()

    assert recovery_contract.source_binding(WindowsSpelling()) == expected
