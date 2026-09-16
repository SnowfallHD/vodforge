from __future__ import annotations

from types import SimpleNamespace

import pytest
from quality_harness.mutation import mutation_detected


@pytest.mark.parametrize(
    ("returncode", "timed_out", "unavailable", "body", "expected"),
    [
        (1, False, False, "<testcase><failure>assert False</failure></testcase>", True),
        (2, False, False, "<testcase><error>ImportError</error></testcase>", False),
        (1, False, False, "<testcase><error>Setup failed</error></testcase>", False),
        (
            1,
            False,
            False,
            "<testcase><failure/></testcase><testcase><error/></testcase>",
            False,
        ),
        (
            1,
            False,
            False,
            "<testcase><failure/></testcase><testcase><skipped/></testcase>",
            False,
        ),
        (1, True, False, "<testcase><failure/></testcase>", False),
        (1, False, True, "<testcase><failure/></testcase>", False),
        (0, False, False, "<testcase/>", False),
        (1, False, False, "", False),
    ],
)
def test_only_executed_assertion_failures_kill_mutations(
    tmp_path, returncode, timed_out, unavailable, body, expected
):
    report = tmp_path / "report.xml"
    report.write_text("<testsuite>" + body + "</testsuite>")
    result = SimpleNamespace(
        returncode=returncode, timed_out=timed_out, unavailable=unavailable
    )
    assert mutation_detected(result, report) is expected


def test_missing_or_invalid_mutation_report_cannot_pass(tmp_path):
    result = SimpleNamespace(returncode=1, timed_out=False, unavailable=False)
    report = tmp_path / "report.xml"
    assert not mutation_detected(result, report)
    report.write_text("<malformed")
    assert not mutation_detected(result, report)
