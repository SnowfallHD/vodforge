import pytest
from types import SimpleNamespace
from quality_harness import native_ui_checks
from quality_harness.native_ui_checks import complete_native_report


@pytest.mark.parametrize(
    "body,expected",
    [
        ("<testcase name='native' />", True),
        ("", False),
        ("<testcase><skipped /></testcase>", False),
        ("<testcase><failure /></testcase>", False),
        ("<testcase><error /></testcase>", False),
    ],
)
def test_native_evidence_requires_executed_successes(tmp_path, body, expected):
    report = tmp_path / "report.xml"
    report.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>")
    assert complete_native_report(report) is expected


def test_missing_native_evidence_fails(tmp_path):
    assert not complete_native_report(tmp_path / "missing.xml")


def test_native_scenario_uses_schema_compatible_evidence(tmp_path, monkeypatch):
    def run(*args, **kwargs):
        (tmp_path / "native.xml").write_text("<testsuite><testcase /></testsuite>")
        return SimpleNamespace(returncode=0, stdout="1 passed")

    monkeypatch.setattr(native_ui_checks, "run_command", run)
    scenario, findings = native_ui_checks.native_surface_contract(tmp_path, tmp_path)
    assert scenario["status"] == "passed"
    assert isinstance(scenario["evidence"], list)
    assert all(isinstance(item, str) for item in scenario["evidence"])
    assert not findings
