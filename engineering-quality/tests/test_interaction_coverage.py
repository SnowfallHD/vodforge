"""Coverage must not silently inherit a successful endpoint or raw receipt."""

import pytest
from quality_harness.interaction_coverage import interaction_coverage
from quality_harness.release_gate import evaluate_engineering_result


def test_legacy_success_and_recorded_timestamps_do_not_establish_coverage():
    scenario = {
        "id": "reliability.cancel_during_slow_download",
        "status": "passed",
        "evidence_tier": "headless_production_pipeline",
        "trace": [{"time": 0}, {"time": 1}],
        "interaction_coverage": {"status": "passed"},
    }
    assert interaction_coverage(scenario)["status"] == "unproven"


def test_native_legacy_tier_is_not_a_static_exemption():
    result = interaction_coverage(
        {
            "id": "unit_static.native_surface_contract",
            "status": "passed",
            "evidence_tier": "unit_static",
        }
    )
    assert result["status"] == "unproven"
    assert result["required_phases"] == ["before", "during", "after"]


def test_new_scenario_defaults_to_unproven():
    assert interaction_coverage({"id": "new.future_owner"})["status"] == "unproven"


def test_static_exemption_is_narrow_and_explained():
    result = interaction_coverage({"id": "maintainability.change_surface"})
    assert result["status"] == "not_applicable" and result["reason"]
    assert not result["required_phases"]
    assert (
        interaction_coverage({"id": "unit_static.repository_suite"})["status"]
        == "unproven"
    )


def test_release_evaluator_blocks_unknown_temporal_coverage_after_scenario_pass():
    scenario_id = "reliability.cancel_during_slow_download"
    checks = evaluate_engineering_result(
        {
            "profile": "normal",
            "scenarios": [
                {"id": scenario_id, "status": "passed", "evidence": ["endpoint OK"]}
            ],
        },
        profile="normal",
    )
    gate = next(c for c in checks if c["id"] == "normal.interaction." + scenario_id)
    assert gate["required"] is True
    assert gate["status"] == "unproven"


@pytest.mark.parametrize(
    "scenario_id",
    [
        "unit_static.native_surface_contract",
        "packaged_app_e2e.full_journey",
    ],
)
def test_ui_usability_is_separate_from_functional_success_and_self_attestation(
    scenario_id,
):
    result = interaction_coverage(
        {
            "id": scenario_id,
            "status": "passed",
            "interaction_coverage": {
                "status": "passed",
                "usability_review": {"status": "passed"},
            },
        }
    )
    review = result["usability_review"]
    assert review["status"] == "unproven"
    assert review["applicability"] == "required"
    assert all(value == "unproven" for value in review["dimensions"].values())
    assert {
        "orientation_navigation",
        "action_hierarchy",
        "progressive_disclosure",
        "visual_hierarchy",
        "sparse_busy_content",
        "feedback",
        "accessibility",
    } <= set(review["dimensions"])
    assert result["phase_review"] == {
        "before": "unproven",
        "during": "unproven",
        "after": "unproven",
    }


def test_static_and_unreviewed_usability_applicability_are_distinct():
    static = interaction_coverage({"id": "maintainability.change_surface"})[
        "usability_review"
    ]
    unknown = interaction_coverage(
        {"id": "new.future_owner", "evidence_tier": "unit_static"}
    )["usability_review"]
    assert static["status"] == static["applicability"] == "not_applicable"
    assert static["reason"] and not static["dimensions"]
    assert unknown["status"] == "unproven"
    assert unknown["applicability"] == "unreviewed"


def test_report_shows_functional_temporal_and_usability_results_together():
    from quality_harness.report import markdown_report, summarize

    scenarios = [
        {
            "id": "unit_static.native_surface_contract",
            "status": "passed",
            "evidence_tier": "unit_static",
            "artifacts": [
                "/tmp/QA evidence/native-evidence.json",
                "/tmp/QA evidence/control [pressed].png",
            ],
        },
        {
            "id": "maintainability.change_surface",
            "status": "passed",
            "evidence_tier": "unit_static",
        },
    ]
    summary, aggregates = summarize(scenarios)
    rendered = markdown_report(
        {
            "run_id": "review-test",
            "profile": "normal",
            "started_at": "2026-09-18T00:00:00Z",
            "summary": summary,
            "aggregate_metrics": aggregates,
            "scenarios": scenarios,
        }
    )
    assert "| Scenario | Functional | Temporal | Usability | Reason |" in rendered
    row = next(
        line
        for line in rendered.splitlines()
        if line.startswith("| unit_static.native_surface_contract |")
    )
    assert "| passed | unproven | unproven (required) |" in row
    assert "before / during / after" in rendered
    assert "](</tmp/QA%20evidence/native-evidence.json>)" in rendered
    assert "](</tmp/QA%20evidence/control%20%5Bpressed%5D.png>)" in rendered


@pytest.mark.parametrize(
    "scenario_id,expected",
    [
        ("unit_static.native_surface_contract", "unproven"),
        ("new.future_owner", "unproven"),
        ("maintainability.change_surface", "passed"),
    ],
)
def test_release_keeps_usability_as_a_separate_required_decision(scenario_id, expected):
    checks = evaluate_engineering_result(
        {
            "profile": "normal",
            "scenarios": [
                {
                    "id": scenario_id,
                    "status": "passed",
                    "usability_review": {"status": "passed"},
                }
            ],
        },
        profile="normal",
    )
    gate = next(c for c in checks if c["id"] == "normal.usability." + scenario_id)
    assert gate["status"] == expected
    assert gate["required"] is True and gate["evidence"]
