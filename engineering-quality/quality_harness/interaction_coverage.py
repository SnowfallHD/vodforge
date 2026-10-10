"""Explicit coverage gaps; scenario success is not temporal acceptance.

This first migration stage inventories every scenario. Domain evaluators must be
enrolled here after their assertions and negative controls are reviewed. Merely
supplying a receipt saying 'passed' cannot establish that enrollment.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .component_interaction import COMPONENT_CONTRACTS, evaluate_component
from .duplicate_interaction import DUPLICATE_CONTRACTS, evaluate_duplicate
from .durability_interaction import DURABILITY_CONTRACTS, evaluate_durability
from .lifecycle_interaction import COMPOSITE_CONTRACTS, evaluate_lifecycle
from .pipeline_interaction import CONTRACTS, evaluate_pipeline
from .public_boundary_interaction import PUBLIC_CONTRACTS, evaluate_public_boundary
from .security_interaction import SECURITY_CONTRACTS, evaluate_security
from .source_suite_interaction import SOURCE_SUITE_CONTRACTS, evaluate_source_suite
from .telemetry_interaction import TELEMETRY_CONTRACTS, evaluate_telemetry
from .transaction_interaction import TRANSACTION_CONTRACTS, evaluate_transaction

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


def _usability_review(
    scenario_id: str, static_reason: str | None, evidence_tier: object = None
) -> dict[str, Any]:
    if static_reason is not None:
        return {
            "status": "not_applicable",
            "applicability": "not_applicable",
            "reason": static_reason,
            "dimensions": {},
        }
    if scenario_id in TELEMETRY_CONTRACTS and evidence_tier == "unit_static":
        return {
            "status": "not_applicable",
            "applicability": "not_applicable",
            "reason": "Reviewed local backend suite, private HTTP/Worker/D1 lifetime and synthetic audit dispatch only. No production ingestion, native interface or audible output is qualified.",
            "dimensions": dict.fromkeys(_USABILITY_DIMENSIONS, "not_applicable"),
            "reviewer": "bounded-local-telemetry-v1 scope review",
        }
    if scenario_id in DURABILITY_CONTRACTS and evidence_tier == "unit_static":
        return {
            "status": "not_applicable",
            "applicability": "not_applicable",
            "reason": "Reviewed optional durable sink episodes or nine exact private-copy source mutation outcomes. No native Activity UI, product usability or repository-wide mutation score is qualified.",
            "dimensions": dict.fromkeys(_USABILITY_DIMENSIONS, "not_applicable"),
            "reviewer": "bounded-durability-v1 scope review",
        }
    if scenario_id in SOURCE_SUITE_CONTRACTS and evidence_tier == "unit_static":
        return {
            "status": "not_applicable",
            "applicability": "not_applicable",
            "reason": "Reviewed maintained source regression scope. Suite admission, exact per-case execution and unchanged source/scene-asset authority do not qualify native product feedback, layout, gestures, devices or usability. All native and packaged acceptance remains separate.",
            "dimensions": dict.fromkeys(_USABILITY_DIMENSIONS, "not_applicable"),
            "reviewer": "explicit-source-suite-v1 scope review",
        }
    if scenario_id in SECURITY_CONTRACTS and evidence_tier == "unit_static":
        return {
            "status": "not_applicable",
            "applicability": "not_applicable",
            "reason": "Reviewed synthetic URL-sink/POSIX or two-loopback-origin component scope. No native surface, external provider request or Windows ACL is qualified; separate product acceptance remains required.",
            "dimensions": dict.fromkeys(_USABILITY_DIMENSIONS, "not_applicable"),
            "reviewer": "bounded-security-v1 scope review",
        }
    if scenario_id in COMPONENT_CONTRACTS and evidence_tier == "unit_static":
        return {
            "status": "not_applicable",
            "applicability": "not_applicable",
            "reason": "Reviewed controlled source/component scope: pure path/argv construction, descendant symlink refusal/private POSIX staging or injected probe-data validation. No rendered native surface, media decoder or full worker commit is observed; separate native/product acceptance remains required.",
            "dimensions": dict.fromkeys(_USABILITY_DIMENSIONS, "not_applicable"),
            "reviewer": "controlled-component-v1 scope review",
        }
    if (
        scenario_id in TRANSACTION_CONTRACTS
        and evidence_tier == TRANSACTION_CONTRACTS[scenario_id][0]
    ):
        return {
            "status": "not_applicable",
            "applicability": "not_applicable",
            "reason": (
                "Reviewed scope: controlled batch-report refusal, durable orphan recovery "
                "or offscreen Qt Library staging ownership. These checks do not render "
                "or operate a native surface; physical restart and native usability "
                "acceptance remain separately required."
            ),
            "dimensions": dict.fromkeys(_USABILITY_DIMENSIONS, "not_applicable"),
            "reviewer": "controlled-transaction-v1 scope review",
        }
    if (
        scenario_id
        in (
            CONTRACTS.keys()
            | COMPOSITE_CONTRACTS.keys()
            | DUPLICATE_CONTRACTS.keys()
            | PUBLIC_CONTRACTS.keys()
        )
        and evidence_tier == "headless_production_pipeline"
    ):
        return {
            "status": "not_applicable",
            "applicability": "not_applicable",
            "reason": (
                "Reviewed scope: this headless worker contract has no rendered "
                "controls, navigation, feedback or accessible native surface. "
                "Its data/lifecycle assertions do not qualify product UX; the "
                "separate native and packaged review remains required."
            ),
            "dimensions": dict.fromkeys(_USABILITY_DIMENSIONS, "not_applicable"),
            "reviewer": "real-worker-staging-control-v1 scope review",
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
    if (
        scenario_id in TELEMETRY_CONTRACTS
        and scenario.get("evidence_tier") == "unit_static"
    ):
        coverage = evaluate_telemetry(scenario)
        coverage["usability_review"] = _usability_review(
            scenario_id, None, scenario.get("evidence_tier")
        )
        return coverage
    if (
        scenario_id in DURABILITY_CONTRACTS
        and scenario.get("evidence_tier") == "unit_static"
    ):
        coverage = evaluate_durability(scenario)
        coverage["usability_review"] = _usability_review(
            scenario_id, None, scenario.get("evidence_tier")
        )
        return coverage
    if (
        scenario_id in SOURCE_SUITE_CONTRACTS
        and scenario.get("evidence_tier") == "unit_static"
    ):
        coverage = evaluate_source_suite(scenario)
        coverage["usability_review"] = _usability_review(
            scenario_id, None, scenario.get("evidence_tier")
        )
        return coverage
    if (
        scenario_id in SECURITY_CONTRACTS
        and scenario.get("evidence_tier") == "unit_static"
    ):
        coverage = evaluate_security(scenario)
        coverage["usability_review"] = _usability_review(
            scenario_id, None, scenario.get("evidence_tier")
        )
        return coverage
    if (
        scenario_id in COMPONENT_CONTRACTS
        and scenario.get("evidence_tier") == "unit_static"
    ):
        coverage = evaluate_component(scenario)
        coverage["usability_review"] = _usability_review(
            scenario_id, None, scenario.get("evidence_tier")
        )
        return coverage
    if (
        scenario_id in TRANSACTION_CONTRACTS
        and scenario.get("evidence_tier") == TRANSACTION_CONTRACTS[scenario_id][0]
    ):
        coverage = evaluate_transaction(scenario)
        coverage["usability_review"] = _usability_review(
            scenario_id, None, scenario.get("evidence_tier")
        )
        return coverage
    if (
        scenario_id in PUBLIC_CONTRACTS
        and scenario.get("evidence_tier") == "headless_production_pipeline"
    ):
        coverage = evaluate_public_boundary(scenario)
        coverage["usability_review"] = _usability_review(
            scenario_id, None, scenario.get("evidence_tier")
        )
        return coverage
    if (
        scenario_id in DUPLICATE_CONTRACTS
        and scenario.get("evidence_tier") == "headless_production_pipeline"
    ):
        coverage = evaluate_duplicate(scenario)
        coverage["usability_review"] = _usability_review(
            scenario_id, None, scenario.get("evidence_tier")
        )
        return coverage
    if (
        scenario_id in COMPOSITE_CONTRACTS
        and scenario.get("evidence_tier") == "headless_production_pipeline"
    ):
        coverage = evaluate_lifecycle(scenario)
        coverage["usability_review"] = _usability_review(
            scenario_id, None, scenario.get("evidence_tier")
        )
        return coverage
    if (
        scenario_id in CONTRACTS
        and scenario.get("evidence_tier") == "headless_production_pipeline"
    ):
        coverage = evaluate_pipeline(scenario)
        coverage["usability_review"] = _usability_review(
            scenario_id, None, scenario.get("evidence_tier")
        )
        return coverage
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
