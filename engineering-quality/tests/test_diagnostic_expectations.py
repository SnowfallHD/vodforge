import pytest
from quality_harness.diagnostic_expectations import verify_scenario_events


def test_late_fault_requires_an_actual_persisted_fault_after_sampling():
    def event(action, **dimensions):
        return {
            "feature": "presentation_operation",
            "action": action,
            "dimensions": {
                "presentation_surface": "watch",
                "presentation_sampling": "healthy_sampled",
                "missing_image_role": "none",
                **dimensions,
            },
        }

    healthy = [event("observed"), event("sampled"), event("settled")]
    with pytest.raises(AssertionError, match="No persisted late control fault"):
        verify_scenario_events("late_fault_after_sampling", healthy)
    fault = event(
        "fault",
        missing_image_role="control",
        presentation_visibility="hidden",
        presentation_scene="retained",
    )
    with pytest.raises(AssertionError):
        verify_scenario_events("late_fault_after_sampling", [fault, *healthy])
    verify_scenario_events("late_fault_after_sampling", [*healthy, fault])


@pytest.mark.parametrize(
    "mutation", ["missing_failure", "wrong_boundary", "wrong_operation", "wrong_step"]
)
def test_opening_evidence_rejects_a_partial_or_unrelated_failure(mutation):
    import copy

    requested = {
        "feature": "playback_operation",
        "action": "requested",
        "dimensions": {
            "operation_id": "captured-opening",
            "operation_step": "1",
            "player_surface": "embedded",
            "playback_origin": "watch",
        },
    }
    failed = {
        **requested,
        "action": "failed",
        "dimensions": {
            **requested["dimensions"],
            "operation_step": "2",
            "playback_failure_boundary": "readiness",
        },
        "failure_reason": "unknown",
        "failure_detail": {"stage": "playback", "failure_code": "timeout"},
    }
    complete = [requested, failed]
    verify_scenario_events("opening_readiness", complete)
    malformed = copy.deepcopy(complete)
    if mutation == "missing_failure":
        malformed.pop()
    elif mutation == "wrong_boundary":
        malformed[-1]["dimensions"]["playback_failure_boundary"] = "initialization"
    elif mutation == "wrong_operation":
        malformed[-1]["dimensions"]["operation_id"] = "unrelated-opening"
    else:
        malformed[-1]["dimensions"]["operation_step"] = "4"
    with pytest.raises(AssertionError):
        verify_scenario_events("opening_readiness", malformed)


@pytest.mark.parametrize(
    "mutation",
    ["missing_count", "wrong_count", "wrong_operation", "wrong_step", "wrong_outcome"],
)
def test_relink_evidence_requires_an_attributable_identity_refusal(mutation):
    import copy

    dimensions = {
        "operation_id": "captured-relink",
        "identity_mismatch_count": "1",
        "verified_count": "0",
        "unresolved_count": "1",
        "collision_count": "0",
        "missing_count": "0",
        "unavailable_count": "0",
    }
    events = [
        {
            "feature": "archive_relink_operation",
            "action": action,
            "dimensions": {**dimensions, "operation_step": str(i + 1)},
        }
        for i, action in enumerate(["requested", "verified", "cancelled"])
    ]
    verify_scenario_events("relink_legacy_format", events)
    wrong = copy.deepcopy(events)
    if mutation == "missing_count":
        wrong[1]["dimensions"].pop("identity_mismatch_count")
    elif mutation == "wrong_count":
        wrong[1]["dimensions"]["identity_mismatch_count"] = "0"
    elif mutation == "wrong_operation":
        wrong[1]["dimensions"]["operation_id"] = "unrelated"
    elif mutation == "wrong_step":
        wrong[1]["dimensions"]["operation_step"] = "4"
    else:
        wrong[-1]["action"] = "committed"
    with pytest.raises((AssertionError, KeyError)):
        verify_scenario_events("relink_legacy_format", wrong)


@pytest.mark.parametrize(
    "mutation",
    ["missing_terminal", "wrong_order", "wrong_identity", "wrong_step", "wrong_size"],
)
def test_queue_readback_requires_complete_attributable_outcome(mutation):
    import copy

    dims = {
        "operation_id": "random-operation",
        "queue_kind": "playlist",
        "queue_order": "ordered",
        "item_count_bucket": "2_5",
        "queue_position_bucket": "2_5",
        "queue_completed_bucket": "2_5",
    }
    events = [
        {
            "feature": "watch_queue_operation",
            "action": action,
            "dimensions": {**dims, "operation_step": str(i + 1)},
        }
        for i, action in enumerate(["requested", "started", "advanced", "completed"])
    ]
    verify_scenario_events("watch_queue_ordered", events)
    wrong = copy.deepcopy(events)
    if mutation == "missing_terminal":
        wrong.pop()
    elif mutation == "wrong_order":
        wrong[-1]["dimensions"]["queue_order"] = "shuffle"
    elif mutation == "wrong_identity":
        wrong[-1]["dimensions"]["operation_id"] = "unrelated"
    elif mutation == "wrong_step":
        wrong[-1]["dimensions"]["operation_step"] = "9"
    else:
        wrong[-1]["dimensions"]["item_count_bucket"] = "1"
    with pytest.raises(AssertionError):
        verify_scenario_events("watch_queue_ordered", wrong)
