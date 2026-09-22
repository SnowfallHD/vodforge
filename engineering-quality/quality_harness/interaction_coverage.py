"""Explicit coverage gaps; scenario success is not temporal acceptance.

This first migration stage inventories every scenario. Domain evaluators must be
enrolled here after their assertions and negative controls are reviewed. Merely
supplying a receipt saying 'passed' cannot establish that enrollment.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_STATIC_EXEMPTIONS = {
    "maintainability.change_surface": (
        "Source change-surface analysis has no running product interaction; "
        "its static debt findings remain governed by the existing gate."
    ),
}


_UI_SCENARIOS = frozenset(
    {
        "unit_static.native_surface_contract",
        "packaged_app_e2e.full_journey",
    }
)
_USABILITY_DIMENSIONS = (
    "orientation_navigation",
    "action_hierarchy",
    "progressive_disclosure",
    "visual_hierarchy",
    "sparse_busy_content",
    "feedback",
    "accessibility",
)


def _usability_review(scenario_id: str, static_reason: str | None) -> dict[str, Any]:
    if static_reason is not None:
        return {
            "status": "not_applicable",
            "applicability": "not_applicable",
            "reason": static_reason,
            "dimensions": {},
        }
    return {
        "status": "unproven",
        "applicability": "required" if scenario_id in _UI_SCENARIOS else "unreviewed",
        "reason": (
            "Usability evidence and reviewer mapping have not been enrolled. "
            "Unknown applicability is not an exemption; functional success "
            "does not establish clarity, restraint or accessible interaction."
        ),
        "dimensions": {name: "unproven" for name in _USABILITY_DIMENSIONS},
    }


def interaction_coverage(scenario: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed for unknown/new scenarios and legacy success-only receipts."""
    scenario_id = str(scenario.get("id", ""))
    reason = _STATIC_EXEMPTIONS.get(scenario_id)
    if reason is not None:
        return {
            "status": "not_applicable",
            "scenario_id": scenario_id,
            "reason": reason,
            "required_phases": [],
            "assertion_mapping": [],
            "phase_review": {},
            "usability_review": _usability_review(scenario_id, reason),
        }
    return {
        "status": "unproven",
        "scenario_id": scenario_id,
        "reason": (
            "Before/during/after requirement-to-assertion review is pending. "
            "Existing scenario status and raw traces do not establish complete "
            "temporal coverage. Preserve their narrower evidence."
        ),
        "required_phases": ["before", "during", "after"],
        "assertion_mapping": [],
        "phase_review": {phase: "unproven" for phase in ("before", "during", "after")},
        "usability_review": _usability_review(scenario_id, None),
    }
