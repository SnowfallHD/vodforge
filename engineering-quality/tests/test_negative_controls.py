from copy import deepcopy

import pytest
from quality_harness.negative_controls import evaluate_native_channels


def trace():
    report = {
        "events": [{"t": 1, "phase": "press"}, {"t": 4, "phase": "release"}],
        "renders": [
            {"t": 0, "canvas_width": 200, "images": [{"bbox": [0, 0, 80, 80]}]},
            {"t": 2, "canvas_width": 240, "images": [{"bbox": [0, 0, 80, 80]}]},
            {"t": 2.5, "canvas_width": 260, "images": [{"bbox": [0, 0, 80, 80]}]},
            {"t": 3, "canvas_width": 280, "images": [{"bbox": [0, 0, 80, 80]}]},
            {"t": 5, "canvas_width": 280, "images": [{"bbox": [0, 0, 80, 80]}]},
        ],
        "windows": [
            {"t": t, "phase": phase, "bounds": {"Width": width, "Height": 200}}
            for t, phase, width in [
                (1.2, "pressed", 200),
                (2, "pressed", 240),
                (3, "pressed", 280),
                (4.2, "released", 280),
                (4.4, "released", 280),
                (4.6, "released", 280),
            ]
        ],
        "errors": [],
    }

    for row in report["renders"]:
        row["layout_width"] = row["canvas_width"] - 4
    return report


@pytest.mark.parametrize(
    "requirement",
    [
        "channels-duplicate-artwork",
        "resize-live-layout",
        "resize-release-following-pointer",
    ],
)
def test_observed_good_behavior_is_not_negative_control_detection(requirement):
    assert evaluate_native_channels(trace(), requirement) == "not_detected"


def test_transient_duplicate_is_detected_even_with_clean_final_render():
    report = trace()
    report["renders"][1]["images"].append({"bbox": [20, 20, 60, 60]})
    report["checks"] = {"all_passed": True}  # Ignored; independent observations win.
    assert evaluate_native_channels(report, "channels-duplicate-artwork") == "detected"
    report["renders"][1]["images"].pop()
    assert (
        evaluate_native_channels(report, "channels-duplicate-artwork") == "not_detected"
    )


def test_delayed_layout_is_detected_despite_correct_final_width():
    report = trace()
    report["renders"] = [report["renders"][0], report["renders"][-1]]
    assert evaluate_native_channels(report, "resize-live-layout") == "detected"


def test_delayed_release_is_detected_despite_stable_final_bounds():
    report = trace()
    report["windows"][-3]["bounds"]["Width"] = 260
    assert (
        evaluate_native_channels(report, "resize-release-following-pointer")
        == "detected"
    )


@pytest.mark.parametrize(
    "damage", ["empty", "dropped", "clock", "no_drag", "driver_error"]
)
def test_incomplete_or_invalid_trace_is_not_detection(damage):
    report = deepcopy(trace())
    if damage == "empty":
        report["renders"] = []
    elif damage == "dropped":
        report["dropped_samples"] = 1
    elif damage == "clock":
        report["windows"][0]["t"] = float("nan")
    elif damage == "no_drag":
        for row in report["windows"]:
            row["bounds"]["Width"] = 200
    else:
        report["errors"] = ["input driver failed"]
    assert evaluate_native_channels(report, "resize-live-layout") == "unproven"


def test_changing_viewport_does_not_prove_content_layout_was_updated():
    report = trace()
    for row in report["renders"][1:-1]:
        row["layout_width"] = report["renders"][0]["layout_width"]
    assert evaluate_native_channels(report, "resize-live-layout") == "detected"
