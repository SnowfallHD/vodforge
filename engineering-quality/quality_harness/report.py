from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .util import distribution

TIER_LABELS = {
    "unit_static": "Unit / static",
    "headless_production_pipeline": "Headless production pipeline",
    "packaged_app_e2e": "Full packaged-app E2E",
}


def summarize(scenarios: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    statuses = Counter(str(scenario.get("status")) for scenario in scenarios)
    pipeline = [
        scenario
        for scenario in scenarios
        if scenario.get("evidence_tier") == "headless_production_pipeline"
    ]
    job_totals = {
        "jobs_attempted": 0,
        "jobs_completed": 0,
        "jobs_failed": 0,
        "jobs_cancelled": 0,
    }
    init_latencies: list[float] = []
    download_times: list[float] = []
    transcode_times: list[float] = []
    throughputs: list[float] = []
    peaks: list[float] = []
    rss_deltas: list[float] = []
    fd_deltas: list[float] = []
    temp_residue = 0
    leaked_processes = 0
    zombie_process_signals = 0
    corrupted_outputs = 0
    for scenario in scenarios:
        metrics = scenario.get("metrics") or {}
        for metric_name in job_totals:
            value = metrics.get(metric_name)
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value >= 0
                and float(value).is_integer()
            ):
                job_totals[metric_name] += int(value)
        corrupted_count = metrics.get("corrupted_final_outputs")
        if (
            isinstance(corrupted_count, (int, float))
            and not isinstance(corrupted_count, bool)
            and corrupted_count >= 0
            and float(corrupted_count).is_integer()
        ):
            corrupted_outputs += int(corrupted_count)
    for scenario in pipeline:
        metrics = scenario.get("metrics") or {}
        if isinstance(metrics.get("job_initialization_seconds"), (int, float)):
            init_latencies.append(float(metrics["job_initialization_seconds"]))
        if isinstance(metrics.get("download_and_postprocess_seconds"), (int, float)):
            download_times.append(float(metrics["download_and_postprocess_seconds"]))
        if isinstance(metrics.get("transcode_seconds"), (int, float)):
            transcode_times.append(float(metrics["transcode_seconds"]))
        if isinstance(
            metrics.get("effective_throughput_bytes_per_second"), (int, float)
        ):
            throughputs.append(float(metrics["effective_throughput_bytes_per_second"]))
        if isinstance(metrics.get("peak_rss_bytes"), (int, float)):
            peaks.append(float(metrics["peak_rss_bytes"]))
        if isinstance(metrics.get("rss_delta_bytes"), (int, float)):
            rss_deltas.append(float(metrics["rss_delta_bytes"]))
        if isinstance(metrics.get("fd_delta"), (int, float)):
            fd_deltas.append(float(metrics["fd_delta"]))
        temp_residue += int(
            metrics.get("staging_entries_after")
            or metrics.get("staging_residue_count")
            or 0
        )
        leaked_processes += int(metrics.get("orphaned_child_processes") or 0)
        zombie_process_signals += int(metrics.get("peak_zombie_processes") or 0)
    by_tier: dict[str, dict[str, int]] = {}
    for tier in TIER_LABELS:
        tier_statuses = Counter(
            str(item.get("status"))
            for item in scenarios
            if item.get("evidence_tier") == tier
        )
        by_tier[tier] = {
            "attempted": sum(tier_statuses.values()),
            "passed": tier_statuses["passed"],
            "failed": tier_statuses["failed"],
            "errors": tier_statuses["error"],
            "skipped": tier_statuses["skipped"],
        }
    summary = {
        "scenarios_attempted": len(scenarios),
        "passed": statuses["passed"],
        "failed": statuses["failed"],
        "errors": statuses["error"],
        "skipped": statuses["skipped"],
        **job_totals,
        "crash_count": sum(
            1
            for item in scenarios
            if item.get("metrics", {}).get("unexpected_process_exit")
        ),
        "corrupted_output_count": corrupted_outputs,
        "leaked_process_count": leaked_processes,
        "zombie_process_signal_count": zombie_process_signals,
        "leaked_temp_file_count": temp_residue,
        "by_evidence_tier": by_tier,
    }
    aggregate = {
        "job_initialization_seconds": distribution(init_latencies),
        "download_and_postprocess_seconds": distribution(download_times),
        "transcode_seconds": distribution(transcode_times),
        "effective_throughput_bytes_per_second": distribution(throughputs, digits=2),
        "peak_rss_bytes": distribution(peaks, digits=0),
        "soak_rss_delta_bytes": distribution(rss_deltas, digits=0),
        "file_descriptor_delta": distribution(fd_deltas, digits=1),
    }
    return summary, aggregate


def comparison(
    current: dict[str, Any], baseline: dict[str, Any] | None
) -> dict[str, Any] | None:
    if baseline is None:
        return None
    current_scenarios = {
        (str(item.get("evidence_tier")), str(item.get("id")))
        for item in current.get("scenarios", [])
    }
    baseline_scenarios = {
        (str(item.get("evidence_tier")), str(item.get("id")))
        for item in baseline.get("scenarios", [])
    }
    current_by_scenario = {
        (str(item.get("evidence_tier")), str(item.get("id"))): item
        for item in current.get("scenarios", [])
    }
    baseline_by_scenario = {
        (str(item.get("evidence_tier")), str(item.get("id"))): item
        for item in baseline.get("scenarios", [])
    }
    same_profile = baseline.get("profile") == current.get("profile")
    same_scenario_set = baseline_scenarios == current_scenarios
    workload_mismatches = [
        f"{tier}:{scenario_id}"
        for tier, scenario_id in sorted(current_scenarios & baseline_scenarios)
        if current_by_scenario[(tier, scenario_id)].get("workload")
        != baseline_by_scenario[(tier, scenario_id)].get("workload")
    ]
    same_workload_contracts = not workload_mismatches
    machine_field_matches = {
        key: current.get("machine", {}).get(key) is not None
        and baseline.get("machine", {}).get(key) == current.get("machine", {}).get(key)
        for key in (
            "system",
            "machine",
            "processor",
            "cpu_count_logical",
            "memory_total_bytes",
        )
    }
    current_commit = current.get("repository", {}).get("commit")
    refusal_reasons: list[str] = []
    if not same_profile:
        refusal_reasons.append(
            f"profile mismatch: current={current.get('profile')!r}, baseline={baseline.get('profile')!r}"
        )
    if not same_scenario_set:
        refusal_reasons.append("scenario/evidence-tier sets differ")
    if workload_mismatches:
        refusal_reasons.append(
            "scenario workload contracts differ: " + ", ".join(workload_mismatches)
        )
    output: dict[str, Any] = {
        "baseline_run_id": baseline.get("run_id"),
        "baseline_machine": baseline.get("machine"),
        "current_profile": current.get("profile"),
        "baseline_profile": baseline.get("profile"),
        "same_profile": same_profile,
        "same_scenario_set": same_scenario_set,
        "same_workload_contracts": same_workload_contracts,
        "workload_mismatches": workload_mismatches,
        "current_scenario_set": [
            f"{tier}:{scenario_id}" for tier, scenario_id in sorted(current_scenarios)
        ],
        "baseline_scenario_set": [
            f"{tier}:{scenario_id}" for tier, scenario_id in sorted(baseline_scenarios)
        ],
        "current_only_scenarios": [
            f"{tier}:{scenario_id}"
            for tier, scenario_id in sorted(current_scenarios - baseline_scenarios)
        ],
        "baseline_only_scenarios": [
            f"{tier}:{scenario_id}"
            for tier, scenario_id in sorted(baseline_scenarios - current_scenarios)
        ],
        "comparable": not refusal_reasons,
        "refusal_reasons": refusal_reasons,
        "same_commit": current_commit is not None
        and baseline.get("repository", {}).get("commit") == current_commit,
        "same_machine": all(machine_field_matches.values()),
        "machine_field_matches": machine_field_matches,
        "metric_deltas": {},
    }
    if refusal_reasons:
        return output
    for metric, values in current.get("aggregate_metrics", {}).items():
        baseline_values = baseline.get("aggregate_metrics", {}).get(metric, {})
        if not isinstance(values, dict) or not isinstance(baseline_values, dict):
            continue
        current_p50 = values.get("p50")
        baseline_p50 = baseline_values.get("p50")
        if isinstance(current_p50, (int, float)) and isinstance(
            baseline_p50, (int, float)
        ):
            output["metric_deltas"][metric] = {
                "current_p50": current_p50,
                "baseline_p50": baseline_p50,
                "absolute_delta": round(current_p50 - baseline_p50, 4),
                "percent_delta": round(
                    (current_p50 - baseline_p50) / baseline_p50 * 100, 2
                )
                if baseline_p50
                else None,
            }
    return output


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.3f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def markdown_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# VODForge engineering-quality report",
        "",
        f"- Run: `{result['run_id']}` (`{result['profile']}`)",
        f"- Commit: `{result.get('repository', {}).get('commit')}` on `{result.get('repository', {}).get('branch')}`",
        f"- Started: {result['started_at']}",
        f"- Duration: {_fmt(result.get('duration_seconds'))} seconds",
        f"- Scenarios: {summary['passed']} passed, {summary['failed']} failed, {summary['errors']} errors, {summary['skipped']} skipped",
        f"- Findings: {len(result.get('findings', []))}",
        "",
        "## Evidence tiers",
        "",
        "These tiers are not interchangeable. A headless production-pipeline pass is not complete-application proof.",
        "",
        "| Tier | Attempted | Passed | Failed | Errors | Skipped |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for tier, label in TIER_LABELS.items():
        counts = summary["by_evidence_tier"][tier]
        lines.append(
            f"| {label} | {counts['attempted']} | {counts['passed']} | {counts['failed']} | {counts['errors']} | {counts['skipped']} |"
        )
    lines.extend(
        [
            "",
            "## Outcome receipts",
            "",
            f"- Jobs attempted/completed/failed/cancelled: {summary.get('jobs_attempted')} / {summary.get('jobs_completed')} / {summary.get('jobs_failed')} / {summary.get('jobs_cancelled')}",
            f"- Crashes: {summary.get('crash_count')}",
            f"- Corrupted final outputs detected: {summary.get('corrupted_output_count')}",
            f"- Leaked child processes after production cleanup: {summary.get('leaked_process_count')}",
            f"- Zombie-process sampling signals: {summary.get('zombie_process_signal_count')}",
            f"- Staging/temp residue signals: {summary.get('leaked_temp_file_count')}",
            "",
            "## Performance and lifecycle signals",
            "",
            "Timing values are run- and machine-specific. Conclusions require comparable machine conditions or an explicit baseline delta.",
            "",
            "| Metric | Count | p50 | p95 | Max |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name, values in result.get("aggregate_metrics", {}).items():
        lines.append(
            f"| {name} | {_fmt(values.get('count'))} | {_fmt(values.get('p50'))} | {_fmt(values.get('p95'))} | {_fmt(values.get('max'))} |"
        )
    lines.extend(["", "## Scenario results", ""])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for scenario in result["scenarios"]:
        grouped[str(scenario.get("evidence_tier"))].append(scenario)
    for tier, label in TIER_LABELS.items():
        lines.extend([f"### {label}", ""])
        for scenario in grouped.get(tier, []):
            lines.append(
                f"- **{str(scenario['status']).upper()}** `{scenario['id']}` — {_fmt(scenario.get('duration_seconds'))}s"
            )
            for evidence in scenario.get("evidence", [])[:6]:
                lines.append(f"  - {str(evidence).replace(chr(10), ' ')}")
        lines.append("")
    findings = result.get("findings", [])
    lines.extend(["## Findings", ""])
    if not findings:
        lines.append(
            "No negative finding survived the executed scenarios. This is bounded to the tiers and cases actually run."
        )
    else:
        severity_order = {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
            "informational": 4,
        }
        for finding in sorted(
            findings,
            key=lambda item: (
                severity_order.get(item.get("severity"), 9),
                item.get("id", ""),
            ),
        ):
            lines.extend(
                [
                    f"### [{str(finding['severity']).upper()}] {finding['title']}",
                    "",
                    f"- Classification: {finding['classification']}",
                    f"- Area: `{finding['area']}`",
                    f"- Scenario: `{finding.get('scenario_id')}`",
                    "- Reproduction:",
                    *[f"  - {step}" for step in finding.get("reproduction", [])],
                    "- Evidence:",
                    *[
                        f"  - {str(item).replace(chr(10), ' ')}"
                        for item in finding.get("evidence", [])
                    ],
                    f"- Suggested fix: {finding['suggested_fix']}",
                    "",
                ]
            )
    comparison_data = result.get("comparison")
    if comparison_data:
        lines.extend(
            [
                "## Baseline comparison",
                "",
                f"- Baseline run: `{comparison_data.get('baseline_run_id')}`",
                f"- Comparable profile, scenario set, and workload: {'yes' if comparison_data.get('comparable') else 'no'}",
                f"- same_commit: {'yes' if comparison_data.get('same_commit') else 'no'}",
                f"- same_machine: {'yes' if comparison_data.get('same_machine') else 'no'}",
                "",
            ]
        )
        if not comparison_data.get("comparable"):
            lines.append(
                "Metric comparison refused because the runs do not execute the same benchmark contract:"
            )
            for reason in comparison_data.get("refusal_reasons", []):
                lines.append(f"- {reason}")
            current_only = comparison_data.get("current_only_scenarios", [])
            baseline_only = comparison_data.get("baseline_only_scenarios", [])
            if current_only:
                lines.append(
                    f"- Current-only scenarios: {', '.join(f'`{item}`' for item in current_only)}"
                )
            if baseline_only:
                lines.append(
                    f"- Baseline-only scenarios: {', '.join(f'`{item}`' for item in baseline_only)}"
                )
        else:
            if not comparison_data.get("same_machine"):
                lines.append(
                    "Machine characteristics differ; performance deltas are descriptive, not controlled evidence."
                )
            if not comparison_data.get("same_commit"):
                lines.append(
                    "Commits differ; deltas may reflect code changes as well as run noise."
                )
            for name, delta in comparison_data.get("metric_deltas", {}).items():
                lines.append(
                    f"- {name}: p50 {_fmt(delta['current_p50'])} vs {_fmt(delta['baseline_p50'])} ({_fmt(delta['percent_delta'])}%)"
                )
        lines.append("")
    lines.extend(
        [
            "## Boundaries and next evidence",
            "",
            "- External media is never treated as deterministic unless its publisher and current run metadata support the assertion.",
            "- YouTube Creative Commons metadata candidates remain download-disabled by default until platform automation authorization is resolved.",
            "- A skipped packaged-app tier means UI/settings/queue/lifecycle integration remains unproven by this run.",
            "- Mutation, forced process-kill restart, low-disk volume, provider playlist scaling, and long-duration packaged-app soak belong to the deep profile or a platform-specific runner.",
            "",
        ]
    )
    return "\n".join(lines)
