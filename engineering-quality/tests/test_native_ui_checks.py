import pytest
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
