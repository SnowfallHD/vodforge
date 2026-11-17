"""A release can't pass the gate unless the app updated itself everywhere."""

from __future__ import annotations

import copy

import pytest
from quality_harness.update_release import MACHINES, SCENARIOS, release_checks

CANDIDATE = {"candidate_version": "0.2.9"}


def journey(platform: str, arch: str, scenario: str, **changes):
    result = {
        "format": "vodforge-update-journey/v2",
        "passed": True,
        "scenario": scenario,
        "machine": {"platform": platform, "arch": arch},
        "baseline_version": "0.2.8",
        "candidate_version": "0.2.9",
        "developer_tools_available": False,
        "telemetry_target": "preview",
        "steps": [{"name": "candidate_reopen", "passed": True}],
    }
    result.update(changes)
    return result


def complete():
    arches = {"arm64": "arm64", "x86_64": "x86_64", None: "AMD64"}
    return [
        journey(platform, arches[arch], scenario)
        for platform, arch, _label in MACHINES
        for scenario in SCENARIOS
    ]


def failed(checks):
    return {check["id"] for check in checks if check["status"] != "passed"}


def test_all_six_journeys_pass_the_gate():
    checks = release_checks(complete(), CANDIDATE)
    assert len(checks) == 6 and not failed(checks)


def test_missing_repair_on_any_machine_blocks_release():
    for index in range(6):
        results = complete()
        missing = results.pop(index)
        assert len(failed(release_checks(results, CANDIDATE))) == 1, missing


def test_a_mac_with_developer_tools_does_not_count():
    """Every QA Mac had Xcode; that is how the 0.2.8 Mac updater shipped broken."""
    results = complete()
    results[0]["developer_tools_available"] = True
    assert failed(release_checks(results, CANDIDATE)) == {
        "updates.darwin.arm64.install_on_quit"
    }


@pytest.mark.parametrize(
    "change",
    [
        {"passed": False},
        {"candidate_version": "0.2.8"},
        {"baseline_version": "0.2.9"},
        {"baseline_version": "0.2.10"},
        {"telemetry_target": "production"},
        {"format": "vodforge-update-journey/v1"},
    ],
)
def test_a_journey_that_proves_less_is_refused(change):
    results = complete()
    results[-1] = {**copy.deepcopy(results[-1]), **change}
    assert failed(release_checks(results, CANDIDATE)) == {"updates.win32.any.repair"}


def test_the_latest_attempt_counts():
    results = complete()
    results.insert(0, journey("win32", "AMD64", "repair", passed=False))
    assert not failed(release_checks(results, CANDIDATE))
