"""Native surface replacement plateau, distinct from managed-cache accounting."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import threading
import time
from itertools import pairwise
from pathlib import Path
from typing import Any

WARMUP_FRAMES = 96
CYCLE_FRAMES = 24
MEASURED_CYCLES = 6
CACHE_LIMIT_BYTES = 8 * 1024 * 1024
# One complete 96-width working set is warmed before repeated replacements.
# Allow one unused-cache generation plus old/new largest native backings.
MAX_BACKING_BYTES = 576 * 321 * 3 * 3 * 8
GROWTH_BUDGET_BYTES = CACHE_LIMIT_BYTES + 2 * MAX_BACKING_BYTES


# NORMAL stays byte-for-byte compatible with retained workload receipts.
# DEEP uses longer repetition and held-out geometry/scales, selected by name.
WORKLOADS = {
    "normal": {
        "warmup_frames": 96,
        "cycle_frames": 24,
        "measured_cycles": 6,
        "working_set": 96,
        "scale": 3,
    },
    "long_scale3": {
        "warmup_frames": 96,
        "cycle_frames": 96,
        "measured_cycles": 10,
        "working_set": 96,
        "scale": 3,
        "width_start": 481,
        "width_step": 1,
        "height": 321,
    },
    "heldout_scale1": {
        "warmup_frames": 122,
        "cycle_frames": 61,
        "measured_cycles": 10,
        "working_set": 61,
        "scale": 1,
        "width_start": 347,
        "width_step": 2,
        "height": 263,
    },
    "heldout_scale2": {
        "warmup_frames": 146,
        "cycle_frames": 73,
        "measured_cycles": 10,
        "working_set": 73,
        "scale": 2,
        "width_start": 389,
        "width_step": 1,
        "height": 287,
    },
}


def backing_budget(workload: dict[str, int]) -> int:
    width = workload.get("width_start", 481) + (
        workload["working_set"] - 1
    ) * workload.get("width_step", 1)
    return width * workload.get("height", 321) * workload["scale"] ** 2 * 8


def loaded_tk_libraries() -> list[dict[str, str]]:
    library = ctypes.CDLL(None)
    library._dyld_image_count.restype = ctypes.c_uint32
    library._dyld_get_image_name.argtypes = [ctypes.c_uint32]
    library._dyld_get_image_name.restype = ctypes.c_char_p
    paths = [
        library._dyld_get_image_name(i).decode()
        for i in range(library._dyld_image_count())
    ]
    return [
        {"path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
        for path in paths
        if "libtcl9tk" in path or "libtcl9.0" in path
    ]


def evaluate_surface_memory(report: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unproven",
        "scope": "finite native replacement RSS plateau",
        "reason": "Incomplete or invalid resource evidence",
        "growth_budget_bytes": GROWTH_BUDGET_BYTES,
    }
    try:
        workload = report["workload"]
        if (
            not isinstance(workload, dict)
            or workload not in WORKLOADS.values()
            or any(type(value) is not int for value in workload.values())
        ):
            return result
        maximum_backing = backing_budget(workload)
        growth_budget = CACHE_LIMIT_BYTES + 2 * maximum_backing
        result["growth_budget_bytes"] = growth_budget
        phases = report["phases"]
        expected = [
            "initial",
            "warm",
            *[f"cycle_{i}" for i in range(1, workload["measured_cycles"] + 1)],
            "teardown",
            "settled",
        ]
        if (
            [p["label"] for p in phases] != expected
            or report["completed"] is not True
            or report["source_unchanged"] is not True
            or report["errors"]
        ):
            return result
        if not any(
            "libtcl9tk" in row["path"] and len(row["sha256"]) == 64
            for row in report["runtime"]["libraries"]
        ):
            return result
        counter_fields = (
            "rss",
            "lifetime_highwater",
            "builds",
            "backing_bytes",
            "cached_bytes",
            "tcl_images",
        )
        for phase in phases:
            if any(
                type(phase[field]) is not int or phase[field] < 0
                for field in counter_fields
            ):
                return result
        if (
            type(report["maximum_cached_bytes"]) is not int
            or report["maximum_cached_bytes"] < 0
        ):
            return result
        # Validate every sample before filtering; NaN and negative prewarm rows
        # must not disappear from an otherwise apparently complete receipt.
        for row in [*phases, *report["samples"]]:
            if (
                type(row["t"]) not in (int, float)
                or not math.isfinite(row["t"])
                or row["t"] < 0
                or type(row["rss"]) is not int
                or row["rss"] <= 0
            ):
                return result
        times = [float(p["t"]) for p in phases]
        if not all(math.isfinite(t) and t >= 0 for t in times) or times != sorted(
            times
        ):
            return result
        if times[-1] - times[-2] < 0.9:
            return result
        for phase in phases:
            if not isinstance(phase["rss"], int) or phase["rss"] <= 0:
                return result
        for index, phase in enumerate(phases[1:-2]):
            if (
                phase["builds"]
                != workload["warmup_frames"] + index * workload["cycle_frames"]
            ):
                return result
        warm = phases[1]["rss"]
        observed = [row for row in report["samples"] if row["t"] >= phases[1]["t"]]
        if len(observed) < 2:
            return result
        for row in observed:
            if (
                not isinstance(row["rss"], int)
                or row["rss"] <= 0
                or not math.isfinite(float(row["t"]))
            ):
                return result
        sample_times = [float(row["t"]) for row in observed]
        if sample_times != sorted(sample_times):
            return result
        gaps = [b - a for a, b in pairwise(sample_times)]
        gaps.extend(
            [sample_times[0] - phases[1]["t"], phases[-1]["t"] - sample_times[-1]]
        )
        if max(gaps) > 0.050 or sample_times[-1] > phases[-1]["t"] + 0.050:
            return result
        measured = [*phases[2:], *observed]
        growth = max(p["rss"] for p in measured) - warm
        cleaned = all(
            p["backing_bytes"] == 0
            and p["cached_bytes"] == 0
            and p["tcl_images"] == phases[0]["tcl_images"]
            for p in phases[-2:]
        )
        bounded_cache = report["maximum_cached_bytes"] <= CACHE_LIMIT_BYTES
        plateau = growth <= growth_budget
        cycle_rss = [phase["rss"] for phase in phases[2:-2]]
        xs = [phase["builds"] for phase in phases[2:-2]]
        x_mean = sum(xs) / len(xs)
        y_mean = sum(cycle_rss) / len(cycle_rss)
        slope = sum(
            (x - x_mean) * (y - y_mean) for x, y in zip(xs, cycle_rss, strict=True)
        ) / sum((x - x_mean) ** 2 for x in xs)
        result.update(
            status="passed" if plateau and cleaned and bounded_cache else "failed",
            reason="Current RSS after measured warmup; lifetime highwater is reported separately",
            warm_rss_bytes=warm,
            maximum_postwarm_growth_bytes=growth,
            trend={
                "cycle_rss_bytes": cycle_rss,
                "fitted_bytes_per_replacement": slope,
                "first_to_last_cycle_growth_bytes": cycle_rss[-1] - cycle_rss[0],
                "measured_replacements": workload["cycle_frames"]
                * workload["measured_cycles"],
                "limits": "Descriptive finite-run trend, not an indefinite leak bound.",
            },
            absolute_footprint={
                "initial_rss_bytes": phases[0]["rss"],
                "warm_rss_bytes": warm,
                "peak_sampled_rss_bytes": max(
                    p["rss"] for p in [*phases, *report["samples"]]
                ),
                "largest_expected_backing_bytes": maximum_backing,
                "unused_cache_budget_bytes": CACHE_LIMIT_BYTES,
                "whole_application_acceptance": "unproven",
                "limits": "RSS includes runtime and allocator allocations; the growth budget "
                "is not an absolute footprint budget or a bound on slow long-run leaks.",
            },
            maximum_observer_gap_seconds=max(gaps),
            assertions={
                "native_rss_plateau": plateau,
                "owned_images_retired": cleaned,
                "unused_cache_bounded": bounded_cache,
            },
        )
    except (KeyError, TypeError, ValueError, IndexError):
        pass
    return result


def run_probe(output: Path, workload_name: str = "normal") -> dict[str, Any]:
    import resource
    import tkinter as tk

    import psutil

    from yt_downloader import ui_chrome

    from .source_identity import source_manifest

    workload = WORKLOADS[workload_name]
    warmup_frames = workload["warmup_frames"]
    cycle_frames = workload["cycle_frames"]
    measured_cycles = workload["measured_cycles"]
    checkout = Path(__file__).resolve().parents[2]
    identity = source_manifest(checkout)
    root = tk.Tk()
    root.geometry("650x450+120+80")
    canvas = tk.Canvas(root, width=620, height=420)
    canvas.pack()
    root.update()
    owner = ui_chrome.CanvasSurfaceCache(canvas)
    prior_scale = ui_chrome.surface_backing_scale
    ui_chrome.surface_backing_scale = lambda _: workload["scale"]
    process = psutil.Process()
    started = time.monotonic()
    samples: list[dict[str, Any]] = []
    phases: list[dict[str, Any]] = []
    errors: list[str] = []
    stop = threading.Event()
    maximum_cached = 0

    def sample() -> None:
        try:
            while not stop.is_set():
                samples.append(
                    {"t": time.monotonic() - started, "rss": process.memory_info().rss}
                )
                stop.wait(0.005)
        except Exception as exc:  # noqa: BLE001 - observer failure cannot become a pass
            errors.append(repr(exc))

    def checkpoint(label: str) -> None:
        phases.append(
            {
                "label": label,
                "t": time.monotonic() - started,
                "rss": process.memory_info().rss,
                "lifetime_highwater": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
                "cached_bytes": owner.cached_bytes,
                "backing_bytes": owner.bytes,
                "builds": owner.builds,
                "tcl_images": len(root.tk.call("image", "names")),
            }
        )

    def finish() -> None:
        checkpoint("settled")
        root.quit()

    def step(index: int = 0) -> None:
        nonlocal maximum_cached
        try:
            canvas.delete("all")
            width = workload.get("width_start", 481) + (
                index % workload["working_set"]
            ) * workload.get("width_step", 1)
            owner.draw(
                (10, 10, 10 + width, 10 + workload.get("height", 321)),
                selected=bool(index % 2),
            )
            if process.memory_info().rss > 2 * 1024**3:
                errors.append("Probe safety stop: RSS exceeded 2 GiB")
                root.quit()
                return
            maximum_cached = max(maximum_cached, owner.cached_bytes)
            count = index + 1
            if count == warmup_frames:
                checkpoint("warm")
            elif count > warmup_frames and (count - warmup_frames) % cycle_frames == 0:
                checkpoint(f"cycle_{(count - warmup_frames) // cycle_frames}")
            if count == warmup_frames + cycle_frames * measured_cycles:
                owner.clear()
                canvas.destroy()
                checkpoint("teardown")
                root.after(1000, finish)
            else:
                root.after(
                    300 if count % cycle_frames == 0 else 16, lambda: step(index + 1)
                )
        except Exception as exc:  # noqa: BLE001 - retain failure and stop the owned loop
            errors.append(repr(exc))
            root.quit()

    observer = threading.Thread(target=sample, daemon=True)
    checkpoint("initial")
    observer.start()
    try:
        root.after(0, step)
        root.after(
            120000 if workload_name != "normal" else 45000,
            lambda: (errors.append("Native probe timed out"), root.quit()),
        )
        root.mainloop()
        runtime = {
            "tk": root.tk.call("package", "require", "Tk"),
            "libraries": loaded_tk_libraries(),
        }
    finally:
        stop.set()
        observer.join(2)
        ui_chrome.surface_backing_scale = prior_scale
        root.destroy()
    report = {
        "pid": os.getpid(),
        "source_manifest": identity,
        "source_unchanged": source_manifest(checkout)["sha256"] == identity["sha256"],
        "runtime": runtime,
        "completed": not observer.is_alive(),
        "workload": dict(workload),
        "phases": phases,
        "samples": samples,
        "errors": errors,
        "maximum_cached_bytes": maximum_cached,
        "limits": [
            "Component source-native probe, not packaged or full-app memory acceptance.",
            "RSS includes allocator retention. Highwater cannot establish current retention.",
            "5ms target sampling may miss transient peaks; phase timestamps and raw samples retained.",
            "No forced GC or global autorelease-pool changes.",
        ],
    }
    report["evaluation"] = evaluate_surface_memory(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workload", choices=tuple(WORKLOADS), default="normal")
    args = parser.parse_args()
    report = run_probe(args.output, args.workload)
    print(json.dumps(report["evaluation"]))
    return 0 if report["evaluation"]["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
