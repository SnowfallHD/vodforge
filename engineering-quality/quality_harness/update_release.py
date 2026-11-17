"""Release checks for the app's own update and Repair paths.

People get every new version through the updater. If it breaks, the only way
forward is the website, and most people never go there, so a release is not
eligible until a signed older build has updated to the candidate through the
app on every shipping machine: Apple silicon, Intel and Windows.

Each machine needs two passing update journeys (runners/update_journey.py):

- install_on_quit: the automatic download installs when the app quits.
- repair: the first download fails; the app must show "Update needs attention"
  by itself and Repair VODForge must install the candidate and reopen it.

On a Mac both must run with the developer tools unavailable to the app
(the journey's default), as on most people's Macs. Before 0.2.9 the updater
ran Apple's stapler, which only exists with Xcode installed, and every QA Mac
had Xcode, so updates passed in QA and failed for the people who mattered.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

FORMAT = "vodforge-update-journey/v2"
SCENARIOS = ("install_on_quit", "repair")
MACHINES = (
    ("darwin", "arm64", "Apple silicon Mac"),
    ("darwin", "x86_64", "Intel Mac"),
    ("win32", None, "Windows PC"),
)


def _version(value: Any) -> tuple[int, ...] | None:
    if not isinstance(value, str) or re.fullmatch(r"\d+\.\d+\.\d+", value) is None:
        return None
    return tuple(int(part) for part in value.split("."))


def _arch(machine: Mapping[str, Any]) -> str:
    arch = str(machine.get("arch") or "").lower()
    return {"aarch64": "arm64", "amd64": "x86_64", "x64": "x86_64"}.get(arch, arch)


def journey_errors(
    result: Mapping[str, Any], *, candidate_version: str | None
) -> list[str]:
    """What keeps one update journey result from counting for a release."""
    errors = []
    if result.get("format") != FORMAT:
        errors.append(f"format is {result.get('format')!r}, not {FORMAT!r}")
    if result.get("passed") is not True:
        failed = [
            str(step.get("name"))
            for step in result.get("steps", [])
            if isinstance(step, Mapping) and step.get("passed") is not True
        ]
        errors.append(f"journey did not pass (failed steps: {failed or 'unknown'})")
    if result.get("candidate_version") != candidate_version:
        errors.append(
            f"tested {result.get('candidate_version')!r}, "
            f"release candidate is {candidate_version!r}"
        )
    baseline = _version(result.get("baseline_version"))
    target = _version(result.get("candidate_version"))
    if baseline is None or target is None or not baseline < target:
        errors.append(
            "baseline must be an older signed build "
            f"({result.get('baseline_version')!r} -> {result.get('candidate_version')!r})"
        )
    machine = result.get("machine")
    machine = machine if isinstance(machine, Mapping) else {}
    if machine.get("platform") == "darwin" and (
        result.get("developer_tools_available") is not False
    ):
        errors.append(
            "a Mac journey must run without developer tools "
            "(most people's Macs have no Xcode)"
        )
    if result.get("telemetry_target") != "preview":
        errors.append("telemetry must go to the preview service")
    return errors


def release_checks(
    results: Sequence[Mapping[str, Any]], candidate: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """One required check per machine and scenario."""
    from .release_gate import _check

    candidate_version = candidate.get("candidate_version")
    checks = []
    for platform, arch, label in MACHINES:
        for scenario in SCENARIOS:
            matching = []
            for result in results:
                machine = result.get("machine")
                machine = machine if isinstance(machine, Mapping) else {}
                if (
                    machine.get("platform") == platform
                    and (arch is None or _arch(machine) == arch)
                    and result.get("scenario") == scenario
                ):
                    matching.append(result)
            evidence: list[str] = []
            if not matching:
                evidence.append(f"No {scenario} update journey from a {label}")
            else:
                # The latest attempt counts; earlier failures stay on record.
                evidence.extend(
                    journey_errors(matching[-1], candidate_version=candidate_version)
                )
            passed = not evidence
            checks.append(
                _check(
                    f"updates.{platform}.{arch or 'any'}.{scenario}",
                    label=f"{label}: update {scenario.replace('_', ' ')}",
                    status="passed" if passed else "failed",
                    required=True,
                    evidence=evidence
                    or [
                        (
                            f"{matching[-1].get('baseline_version')} -> "
                            f"{matching[-1].get('candidate_version')} passed"
                        )
                    ],
                )
            )
    return checks
