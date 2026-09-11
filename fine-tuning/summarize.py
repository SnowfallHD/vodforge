"""Print within-run GPU versus CPU comparisons as portable CSV."""

from __future__ import annotations

import argparse
import csv
import json
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt")
    args = parser.parse_args()
    with open(args.receipt, encoding="utf-8") as handle:
        run = json.load(handle)
    if run.get("status") != "complete":
        print(
            "Incomplete calibration: comparisons are exploratory only.", file=sys.stderr
        )
    cpu = {
        (row["fixture"], row["preset"]): row
        for row in run["results"]
        if row["encoder"] == "cpu"
    }
    writer = csv.writer(sys.stdout)
    writer.writerow(
        [
            "fixture",
            "preset",
            "cq",
            "speed",
            "cpu_mb",
            "nvenc_mb",
            "size_ratio",
            "cpu_vmaf",
            "nvenc_vmaf",
            "vmaf_delta",
            "cpu_seconds",
            "nvenc_seconds",
            "speedup",
        ]
    )
    for row in run["results"]:
        if row["encoder"] != "nvenc":
            continue
        base = cpu[(row["fixture"], row["preset"])]
        speed = row["speed"]
        if speed is None and "-preset" in row["command"]:
            speed = row["command"][row["command"].index("-preset") + 1]
        writer.writerow(
            [
                row["fixture"],
                row["preset"],
                row["cq"],
                speed,
                round(base["bytes"] / 1e6, 3),
                round(row["bytes"] / 1e6, 3),
                round(row["bytes"] / base["bytes"], 3),
                base["vmaf"],
                row["vmaf"],
                round(row["vmaf"] - base["vmaf"], 3),
                base["encode_seconds"],
                row["encode_seconds"],
                round(base["encode_seconds"] / row["encode_seconds"], 3),
            ]
        )


if __name__ == "__main__":
    main()
