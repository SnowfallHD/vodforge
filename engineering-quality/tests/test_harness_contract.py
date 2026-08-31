from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from quality_harness.packaged_e2e import (
    DEEP_REQUIRED_UI_EVENTS,
    SMOKE_REQUIRED_UI_EVENTS,
)
from quality_harness.pipeline import _diagnostic_timing
from quality_harness.reliability_static import activity_log_failure_receipt_probe
from quality_harness.report import TIER_LABELS, comparison, markdown_report, summarize

HARNESS_ROOT = Path(__file__).resolve().parents[1]


def test_activity_log_failure_probe_proves_receipt_deduplication_and_recovery(
    tmp_path: Path,
) -> None:
    scenario, findings = activity_log_failure_receipt_probe(tmp_path)

    assert scenario["status"] == "passed"
    assert scenario["evidence_tier"] == "unit_static"
    assert scenario["metrics"] == {
        "first_failure_receipt_count": 1,
        "recovered": True,
        "new_failure_total_receipt_count": 2,
        "secret_free_receipts": True,
        "failed_handle_detached": True,
    }
    assert findings == []


def test_manifest_separates_content_rights_from_platform_automation() -> None:
    manifest = json.loads(
        (HARNESS_ROOT / "corpus" / "manifest.json").read_text(encoding="utf-8")
    )
    items = manifest["items"]
    youtube = [item for item in items if "youtube.com" in str(item.get("url"))]
    assert youtube
    assert all(
        item.get("platform_automation_status") == "needs-review" for item in youtube
    )
    assert all(item.get("default_media_download") is False for item in youtube)
    assert any(
        item.get("default_media_download") is True
        for item in items
        if item.get("source_kind") == "public"
    )


def test_result_schema_names_all_three_non_interchangeable_tiers() -> None:
    schema = json.loads(
        (HARNESS_ROOT / "schemas" / "run-result.schema.json").read_text(
            encoding="utf-8"
        )
    )
    scenario_schema = schema["properties"]["scenarios"]["items"]
    assert scenario_schema["properties"]["status"]["enum"] == [
        "passed",
        "failed",
        "error",
        "skipped",
    ]
    assert scenario_schema["properties"]["evidence_tier"]["enum"] == list(TIER_LABELS)
    assert "evidence_tier" in scenario_schema["required"]
    assert set(TIER_LABELS) == {
        "unit_static",
        "headless_production_pipeline",
        "packaged_app_e2e",
    }


def test_summary_does_not_promote_headless_to_packaged_e2e() -> None:
    summary, _aggregate = summarize(
        [
            {
                "id": "headless",
                "status": "passed",
                "evidence_tier": "headless_production_pipeline",
                "metrics": {},
            },
            {
                "id": "e2e",
                "status": "skipped",
                "evidence_tier": "packaged_app_e2e",
                "metrics": {},
            },
        ]
    )
    assert summary["by_evidence_tier"]["headless_production_pipeline"]["passed"] == 1
    assert summary["by_evidence_tier"]["packaged_app_e2e"]["passed"] == 0
    assert summary["by_evidence_tier"]["packaged_app_e2e"]["skipped"] == 1


def test_summary_aggregates_only_explicit_job_outcomes() -> None:
    summary, _aggregate = summarize(
        [
            {
                "id": "expected-clean-failure",
                "status": "passed",
                "evidence_tier": "headless_production_pipeline",
                "metrics": {
                    "jobs_attempted": 1,
                    "jobs_completed": 0,
                    "jobs_failed": 1,
                    "jobs_cancelled": 0,
                    "wrong_contract_artifacts_accepted": 2,
                },
            },
            {
                "id": "successful-job",
                "status": "failed",
                "evidence_tier": "packaged_app_e2e",
                "metrics": {
                    "jobs_attempted": 2,
                    "jobs_completed": 1,
                    "jobs_failed": 1,
                    "jobs_cancelled": 0,
                    "corrupted_final_outputs": 1,
                },
            },
            {
                "id": "no-job-static-pass",
                "status": "passed",
                "evidence_tier": "unit_static",
                "metrics": {},
            },
        ]
    )
    assert summary["jobs_attempted"] == 3
    assert summary["jobs_completed"] == 1
    assert summary["jobs_failed"] == 2
    assert summary["jobs_cancelled"] == 0
    assert summary["corrupted_output_count"] == 1


def _comparison_run(
    *, profile: str, scenario_ids: list[str], commit: str = "abc"
) -> dict[str, Any]:
    return {
        "run_id": f"{profile}-run",
        "profile": profile,
        "repository": {"commit": commit},
        "machine": {
            "system": "Darwin",
            "machine": "arm64",
            "processor": "arm",
            "cpu_count_logical": 10,
            "memory_total_bytes": 16,
        },
        "scenarios": [
            {"id": scenario_id, "evidence_tier": "headless_production_pipeline"}
            for scenario_id in scenario_ids
        ],
        "aggregate_metrics": {"latency": {"p50": 2.0}},
    }


def test_comparison_refuses_unlike_profile_or_scenario_set() -> None:
    current = _comparison_run(profile="normal", scenario_ids=["a", "b"])
    baseline = _comparison_run(profile="deep", scenario_ids=["a"])
    result = comparison(current, baseline)
    assert result is not None
    assert result["comparable"] is False
    assert result["same_profile"] is False
    assert result["same_scenario_set"] is False
    assert result["metric_deltas"] == {}
    assert result["refusal_reasons"] == [
        "profile mismatch: current='normal', baseline='deep'",
        "scenario/evidence-tier sets differ",
    ]


def test_comparison_refuses_different_scenario_workload_contracts() -> None:
    current = _comparison_run(
        profile="deep", scenario_ids=["lifecycle.repeated_job_soak"]
    )
    baseline = _comparison_run(
        profile="deep", scenario_ids=["lifecycle.repeated_job_soak"]
    )
    current["scenarios"][0]["workload"] = {"jobs": 50, "contract": "v2"}
    baseline["scenarios"][0]["workload"] = {"jobs": 100, "contract": "v2"}

    result = comparison(current, baseline)

    assert result is not None
    assert result["comparable"] is False
    assert result["same_profile"] is True
    assert result["same_scenario_set"] is True
    assert result["same_workload_contracts"] is False
    assert result["workload_mismatches"] == [
        "headless_production_pipeline:lifecycle.repeated_job_soak"
    ]
    assert result["refusal_reasons"] == [
        (
            "scenario workload contracts differ: "
            "headless_production_pipeline:lifecycle.repeated_job_soak"
        )
    ]
    assert result["metric_deltas"] == {}


def test_markdown_exposes_machine_and_commit_comparability() -> None:
    current = _comparison_run(profile="normal", scenario_ids=["a"], commit="new")
    baseline = _comparison_run(profile="normal", scenario_ids=["a"], commit="old")
    comparison_data = comparison(current, baseline)
    assert comparison_data is not None
    result = {
        **current,
        "started_at": "2026-08-29T00:00:00Z",
        "duration_seconds": 1.0,
        "summary": {
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "jobs_attempted": 1,
            "jobs_completed": 1,
            "jobs_failed": 0,
            "jobs_cancelled": 0,
            "crash_count": 0,
            "corrupted_output_count": 0,
            "leaked_process_count": 0,
            "leaked_temp_file_count": 0,
            "by_evidence_tier": {
                tier: {
                    "attempted": 1 if tier == "headless_production_pipeline" else 0,
                    "passed": 1 if tier == "headless_production_pipeline" else 0,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                }
                for tier in TIER_LABELS
            },
        },
        "scenarios": [
            {
                "id": "a",
                "category": "correctness",
                "evidence_tier": "headless_production_pipeline",
                "status": "passed",
                "duration_seconds": 1.0,
                "evidence": [],
            }
        ],
        "findings": [],
        "comparison": comparison_data,
    }
    rendered = markdown_report(result)
    assert "- same_commit: no" in rendered
    assert "- same_machine: yes" in rendered


def test_packaged_profiles_require_restart_and_deep_queue_cancellation() -> None:
    assert {
        "restart_requested",
        "restart_observed",
        "library_observed",
    } <= SMOKE_REQUIRED_UI_EVENTS
    assert {
        "slow_run_started",
        "second_run_queued",
        "cancellation_requested",
        "cancellation_observed",
        "queued_run_started",
        "queued_run_completion_observed",
    } <= DEEP_REQUIRED_UI_EVENTS


def test_diagnostic_timing_sums_playlist_items_without_conflating_stages() -> None:
    parsed = _diagnostic_timing(
        "analysis completed elapsed_seconds=0.2\n"
        "download and yt-dlp post-processing elapsed_seconds=0.4\n"
        "transcode elapsed_seconds=0.8\n"
        "transcode elapsed_seconds=1.2\n"
    )
    assert parsed["source_analysis_seconds"] == 0.2
    assert parsed["download_and_postprocess_seconds"] == 0.4
    assert parsed["transcode_seconds"] == 2.0
    assert parsed["transcode_seconds_samples"] == [0.8, 1.2]


@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    title=st.text(min_size=0, max_size=300),
    uploader=st.text(min_size=0, max_size=120),
    playlist=st.text(min_size=0, max_size=120),
    video_id=st.text(min_size=0, max_size=80),
)
def test_generated_metadata_never_lexically_escapes_output_root(
    tmp_path: Path,
    title: str,
    uploader: str,
    playlist: str,
    video_id: str,
) -> None:
    from yt_downloader.app import resolved_video_output_target

    output_root = tmp_path / "output"
    info = {
        "title": title,
        "uploader": uploader,
        "playlist_title": playlist,
        "id": video_id,
    }
    try:
        target_dir, target_name = resolved_video_output_target(
            output_root, info, ".mp4"
        )
    except ValueError:
        return
    assert os.path.commonpath([str(output_root), str(target_dir / target_name)]) == str(
        output_root
    )
    assert not Path(target_name).is_absolute()
    assert "/" not in target_name and "\\" not in target_name


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(payload=st.text(min_size=1, max_size=200))
def test_ffmpeg_builder_keeps_untrusted_path_as_one_argv_element(
    tmp_path: Path, payload: str
) -> None:
    from yt_downloader.app import build_vod_ffmpeg_command

    source = tmp_path / payload.replace("\x00", "_")
    output = tmp_path / "output.mp4"
    command = build_vod_ffmpeg_command("ffmpeg", source, output)
    assert str(source) in command
    assert command.count(str(source)) == 1
    assert command[-1] == str(output)
