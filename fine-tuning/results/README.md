# Recorded tuning results

The September 10, 2026 NVIDIA study uses a **GeForce RTX 2080 Ti, driver 610.88,
Windows 10 build 19045, and FFmpeg 9.0.1 (Gyan essentials)**. CPU and GPU outputs
were measured on that same host. See [the methodology](../README.md) before
interpreting quality scores or timing.

- [Decision, comparisons and verification](2026-09-10-nvenc-report.md)
- [Unused-segment receipts](2026-09-10-rtx2080ti-holdout.json)
- [Unused-segment comparison CSV](2026-09-10-rtx2080ti-holdout.csv)
- [Final four-scene receipts](2026-09-10-rtx2080ti-final.json)
- [Final CPU/GPU comparison CSV](2026-09-10-rtx2080ti-final.csv)
- [Calibration history](2026-09-10-rtx2080ti-calibration.json)

Calibration has explicit interrupted/complete audit status. Sweep 03 uses sampled
VMAF and is exploratory only; the other accepted scores use every frame. Exact
commands are authoritative for options (including p6, temporal AQ and multipass)
when the optional sweep-specific `speed` or `spatial_aq` fields are null.

The CLI source label names the starting checkout. The `production_files` hashes
in final receipts match the corresponding files in source checkpoint `71763a9`;
those hashes identify the measured implementation, including uncommitted tuning
changes at run time. The runner hash records the actual experiment script;
subsequent report-field additions do not change encoder settings or scoring.

Generated media and per-frame VMAF logs are not committed. Input/output hashes
allow verification against a locally reproduced corpus. No original footage,
user Library, source URL, private directory or telemetry data is distributed.

In older exploratory receipts, `spatial_aq` stores the CLI AQ selector, including
`temporal`; the command records the actual flags. The accepted final and holdout
runs use temporal AQ, with spatial AQ disabled.
