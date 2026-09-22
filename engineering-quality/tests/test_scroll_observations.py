from quality_harness.scroll_observations import evaluate_scroll_observations


def receipt():
    return {
        "completed": True,
        "errors": [],
        "events": [{"t": 0.12 + i * 0.02} for i in range(31)],
        "handled": [
            {
                "begin": 0.13 + i * 0.02,
                "end": 0.131 + i * 0.02,
                "before": i * 12,
                "after": (i + 1) * 12,
            }
            for i in range(31)
        ],
        "frames": [
            {
                "begin": i * 0.02,
                "end": i * 0.02 + 0.003,
                "sha256": f"{max(0, i - 6):064x}",
            }
            for i in range(42)
        ],
    }


def test_responsive_pixel_sequence_is_a_positive_control():
    assert evaluate_scroll_observations(receipt())["status"] == "passed"


def test_transient_freeze_fails_even_when_callbacks_and_final_position_succeed():
    report = receipt()
    for frame in report["frames"][8:22]:
        frame["sha256"] = report["frames"][7]["sha256"]
    evaluated = evaluate_scroll_observations(report)
    assert evaluated["status"] == "failed"
    assert not evaluated["assertions"]["no_sampled_pixel_freeze_over_100ms"]


def test_delayed_first_pixels_fail_despite_event_handling():
    report = receipt()
    for frame in report["frames"][:18]:
        frame["sha256"] = "0" * 64
    result = evaluate_scroll_observations(report)
    assert result["status"] == "failed"
    assert not result["assertions"]["first_pixel_change_within_100ms"]


def test_missing_interval_or_observer_failure_is_unproven():
    report = receipt()
    del report["frames"][10:15]
    assert evaluate_scroll_observations(report)["status"] == "unproven"
    report = receipt()
    report["errors"] = ["capture failed"]
    assert evaluate_scroll_observations(report)["status"] == "unproven"


def test_scroll_boundary_does_not_require_pixels_to_keep_moving():
    report = receipt()
    for row in report["handled"][12:]:
        row["before"] = row["after"] = 144
    frozen = report["frames"][19]["sha256"]
    for frame in report["frames"][20:]:
        frame["sha256"] = frozen
    assert evaluate_scroll_observations(report)["status"] == "passed"


def test_pixels_may_be_presented_before_scroll_callback_returns():
    report = receipt()
    for row in report["handled"]:
        row["end"] = row["begin"] + 0.04
    assert evaluate_scroll_observations(report)["status"] == "passed"


def tail_receipt(present_at):
    report = receipt()
    report["handled"][-1].update(begin=0.752, end=0.754)
    last_before = report["frames"][35]["sha256"]
    report["frames"] = report["frames"][:36] + [
        {
            "begin": i * 0.02,
            "end": i * 0.02 + 0.003,
            "sha256": last_before if i * 0.02 < present_at else "f" * 64,
        }
        for i in range(36, 51)
    ]
    return report


def test_final_movement_can_present_after_first_post_input_frame():
    # Last input was posted at .72; handling begins at .752 and pixels are
    # observed at .803. This is inside the independently specified 100ms limit.
    result = evaluate_scroll_observations(tail_receipt(0.80))
    assert result["status"] == "passed"
    assert result["maximum_movement_to_pixel_change_upper_ms"] <= 100


def test_late_final_pixels_still_fail_with_full_tail_evidence():
    # A later settled frame must not excuse a response beyond 100ms.
    result = evaluate_scroll_observations(tail_receipt(0.90))
    assert result["status"] == "failed"
    assert not result["assertions"]["no_sampled_pixel_freeze_over_100ms"]


def test_missing_tail_cannot_prove_final_movement_failed_or_passed():
    report = tail_receipt(0.80)
    report["frames"] = [f for f in report["frames"] if f["begin"] <= 0.78]
    assert evaluate_scroll_observations(report)["status"] == "unproven"


def test_fast_final_catchup_does_not_erase_frozen_middle_responses():
    report = receipt()
    for frame in report["frames"][9:22]:
        frame["sha256"] = report["frames"][8]["sha256"]
    result = evaluate_scroll_observations(report)
    assert result["status"] == "failed"
    bounds = result["movement_response_bounds"]
    assert bounds[-1]["next_changed_frame_upper_ms"] < 100
    assert any(row["next_changed_frame_upper_ms"] > 100 for row in bounds[:-1])
    assert not result["assertions"]["no_sampled_pixel_freeze_over_100ms"]


def test_sub_100ms_jumps_do_not_certify_continuous_smoothness():
    report = receipt()
    for index, frame in enumerate(report["frames"]):
        frame["sha256"] = f"{max(0, (index - 6) // 4):064x}"
    result = evaluate_scroll_observations(report)
    assert result["status"] == "passed"
    assert result["claim_scope"] == "sampled_response_latency_only"
    assert result["continuous_smoothness"] == "unproven"
    assert len(result["movement_response_bounds"]) == len(report["handled"])
