# Generated reports

Each run writes a machine-readable `results.json`, a human-readable `summary.md`, raw command evidence, and run-local diagnostics under a timestamped directory here. Generated run directories are intentionally ignored because they contain machine-specific measurements and can be large.

Promote a report into version control only when it is an intentionally reviewed baseline. Compare future runs with `--compare path/to/results.json`; the report records both raw values and deltas rather than treating one machine's timing as a universal threshold.
