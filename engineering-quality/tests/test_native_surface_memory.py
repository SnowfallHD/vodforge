"""Retained native RSS cannot be inferred from image counts or lifetime peaks."""

from copy import deepcopy

import pytest
from quality_harness.native_surface_memory import (
    GROWTH_BUDGET_BYTES,
    evaluate_surface_memory,
)


def evidence():
    labels = [
        "initial",
        "warm",
        *[f"cycle_{i}" for i in range(1, 7)],
        "teardown",
        "settled",
    ]
    phases = []
    for i, label in enumerate(labels):
        closed = label in {"initial", "teardown", "settled"}
        phases.append(
            {
                "label": label,
                "t": float(i),
                "rss": 120_000_000 + min(i, 1) * 40_000_000,
                "lifetime_highwater": 2_000_000_000,
                "builds": 0 if i == 0 else min(240, 96 + (i - 1) * 24),
                "backing_bytes": 0 if closed else 12_000_000,
                "cached_bytes": 0,
                "tcl_images": 15 if closed else 16,
            }
        )
    return {
        "completed": True,
        "source_unchanged": True,
        "errors": [],
        "runtime": {
            "libraries": [{"path": "/qa/libtcl9tk9.0.dylib", "sha256": "a" * 64}]
        },
        "workload": {
            "warmup_frames": 96,
            "cycle_frames": 24,
            "measured_cycles": 6,
            "working_set": 96,
            "scale": 3,
        },
        "phases": phases,
        "maximum_cached_bytes": 0,
        "samples": [{"t": i / 100, "rss": 160_000_000} for i in range(100, 901)],
    }


def test_plateau_uses_current_rss_not_lifetime_highwater():
    assert evaluate_surface_memory(evidence())["status"] == "passed"


def test_native_growth_fails_despite_empty_cache_and_retired_tcl_images():
    report = evidence()
    for index, phase in enumerate(report["phases"][2:]):
        phase["rss"] += (index + 1) * GROWTH_BUDGET_BYTES
    result = evaluate_surface_memory(report)
    assert result["status"] == "failed"
    assert not result["assertions"]["native_rss_plateau"]
    assert result["assertions"]["owned_images_retired"]


@pytest.mark.parametrize("missing", ["warm", "cycle_3", "settled"])
def test_missing_phase_cannot_establish_plateau(missing):
    report = evidence()
    report["phases"] = [p for p in report["phases"] if p["label"] != missing]
    assert evaluate_surface_memory(report)["status"] == "unproven"


@pytest.mark.parametrize(
    "fault", ["source", "runtime", "observer", "work", "unfinished", "settle"]
)
def test_invalid_execution_stays_unproven(fault):
    report = deepcopy(evidence())
    if fault == "source":
        report["source_unchanged"] = False
    elif fault == "runtime":
        report["runtime"]["libraries"] = []
    elif fault == "observer":
        report["errors"] = ["sampler failed"]
    elif fault == "work":
        report["phases"][3]["builds"] -= 1
    elif fault == "unfinished":
        report["completed"] = False
    else:
        report["phases"][-1]["t"] = report["phases"][-2]["t"] + 0.1
    assert evaluate_surface_memory(report)["status"] == "unproven"


def test_stable_rss_does_not_excuse_unretired_images():
    report = evidence()
    report["phases"][-1]["tcl_images"] += 1
    result = evaluate_surface_memory(report)
    assert result["status"] == "failed"
    assert not result["assertions"]["owned_images_retired"]


def test_inflight_retention_cannot_hide_behind_recovered_endpoint():
    report = evidence()
    report["phases"][4]["rss"] += GROWTH_BUDGET_BYTES + 1
    result = evaluate_surface_memory(report)
    assert result["status"] == "failed"
    assert result["assertions"]["owned_images_retired"]


def test_native_allocation_spike_between_checkpoints_is_not_hidden():
    report = evidence()
    report["samples"][250]["rss"] += GROWTH_BUDGET_BYTES + 1
    assert evaluate_surface_memory(report)["status"] == "failed"


def test_missing_during_operation_samples_are_unproven():
    report = evidence()
    report["samples"] = report["samples"][::20]
    assert evaluate_surface_memory(report)["status"] == "unproven"


@pytest.mark.parametrize(
    "value", [True, False, -1, float("nan"), float("inf"), "0", None]
)
@pytest.mark.parametrize(
    "field",
    [
        "rss",
        "lifetime_highwater",
        "builds",
        "backing_bytes",
        "cached_bytes",
        "tcl_images",
    ],
)
def test_invalid_phase_counters_cannot_qualify(field, value):
    report = evidence()
    report["phases"][0][field] = value
    assert evaluate_surface_memory(report)["status"] == "unproven"


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf"), "0"])
def test_invalid_peak_cache_counter_cannot_qualify(value):
    report = evidence()
    report["maximum_cached_bytes"] = value
    assert evaluate_surface_memory(report)["status"] == "unproven"


@pytest.mark.parametrize(
    "field,value",
    [
        ("t", float("nan")),
        ("t", -1),
        ("t", True),
        ("t", "0"),
        ("rss", True),
        ("rss", -1),
        ("rss", float("inf")),
    ],
)
def test_invalid_prewarm_samples_cannot_hide_in_filter(field, value):
    report = evidence()
    report["samples"].insert(0, {"t": 0.5, "rss": 120_000_000})
    report["samples"][0][field] = value
    assert evaluate_surface_memory(report)["status"] == "unproven"


def test_large_warm_footprint_is_reported_without_claiming_absolute_acceptance():
    report = evidence()
    for row in [*report["phases"], *report["samples"]]:
        row["rss"] += 2_000_000_000
    result = evaluate_surface_memory(report)
    assert result["status"] == "passed"
    assert result["absolute_footprint"]["warm_rss_bytes"] == 2_160_000_000
    assert result["absolute_footprint"]["whole_application_acceptance"] == "unproven"


def heldout_evidence():
    report = evidence()
    report["workload"] = {
        "warmup_frames": 122,
        "cycle_frames": 61,
        "measured_cycles": 10,
        "working_set": 61,
        "scale": 1,
        "width_start": 347,
        "width_step": 2,
        "height": 263,
    }
    template = report["phases"][2]
    labels = [
        "initial",
        "warm",
        *[f"cycle_{i}" for i in range(1, 11)],
        "teardown",
        "settled",
    ]
    phases = []
    for i, label in enumerate(labels):
        row = dict(template, label=label, t=float(i), builds=122 + max(0, i - 1) * 61)
        if label == "initial":
            row.update(builds=0, rss=120_000_000, backing_bytes=0, tcl_images=15)
        if label in {"teardown", "settled"}:
            row.update(builds=732, backing_bytes=0, cached_bytes=0, tcl_images=15)
        phases.append(row)
    report["phases"] = phases
    report["samples"] = [{"t": i / 100, "rss": 160_000_000} for i in range(1301)]
    return report


def test_deep_heldout_plateau_reports_absolute_and_trend_separately():
    result = evaluate_surface_memory(heldout_evidence())
    assert result["status"] == "passed"
    assert result["trend"]["measured_replacements"] == 610
    assert result["trend"]["fitted_bytes_per_replacement"] == 0
    assert result["absolute_footprint"]["whole_application_acceptance"] == "unproven"
    assert result["growth_budget_bytes"] == 8 * 1024 * 1024 + 2 * 467 * 263 * 8


def test_longer_heldout_work_detects_slow_growth_inside_short_run_allowance():
    report = heldout_evidence()
    # 20 KB per replacement is smaller than the prior short-run allowance,
    # but becomes visible over this held-out 610-replacement workload.
    for phase in report["phases"][2:]:
        phase["rss"] += max(0, phase["builds"] - 122) * 20_000
    result = evaluate_surface_memory(report)
    assert max(p["rss"] for p in report["phases"]) - 160_000_000 < GROWTH_BUDGET_BYTES
    assert result["status"] == "failed"
    assert result["trend"]["fitted_bytes_per_replacement"] == pytest.approx(20_000)


@pytest.mark.parametrize(
    "change", ["shortened", "unknown_scale", "bool_scale", "unknown_size"]
)
def test_deep_workload_cannot_be_redefined_by_its_receipt(change):
    report = heldout_evidence()
    if change == "shortened":
        report["workload"]["measured_cycles"] = 2
    elif change == "unknown_scale":
        report["workload"]["scale"] = 4
    elif change == "bool_scale":
        report["workload"]["scale"] = True
    else:
        report["workload"]["width_start"] = 300
    assert evaluate_surface_memory(report)["status"] == "unproven"
