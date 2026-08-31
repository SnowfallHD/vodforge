from __future__ import annotations

import gc
import json
import weakref
from pathlib import Path
from typing import Any, cast

from quality_harness import scenarios as scenarios_module
from quality_harness.cli import _parser
from quality_harness.metrics import (
    LifecycleCheckpointRecorder,
    lifecycle_growth_summary,
)


def _isolate_application_data(monkeypatch: Any, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    return home


def test_lifecycle_growth_summary_describes_warmup_and_tail_without_verdict() -> None:
    summary = lifecycle_growth_summary([100, 180, 200, 210, 220], warmup_jobs=2)

    assert summary == {
        "sample_count": 5,
        "first": 100,
        "last": 220,
        "delta": 120,
        "linear_slope_per_job": 27.0,
        "post_warmup_sample_count": 3,
        "post_warmup_delta": 20,
        "post_warmup_linear_slope_per_job": 10.0,
        "new_high_count": 4,
    }
    assert "leak" not in summary


def test_normal_checkpoint_records_incrementally_and_marks_ui_unavailable(
    monkeypatch: Any, tmp_path: Path
) -> None:
    _isolate_application_data(monkeypatch, tmp_path)
    run_root = tmp_path / "run"
    (run_root / "tmp").mkdir(parents=True)
    recorder = LifecycleCheckpointRecorder(run_root, jobs=1, detailed=False)

    recorder.start()
    recorder.before_job(1)
    recorder.after_job(1, extra={"case_id": "one"})
    recorder.finish()

    samples = [
        json.loads(line)
        for line in recorder.samples_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [sample["phase"] for sample in samples] == [
        "baseline",
        "before_job",
        "after_job",
    ]
    final = samples[-1]
    assert final["job"] == {"case_id": "one"}
    assert final["gc"]["collected_by_forced_full_gc"] >= 0
    assert final["gc_tracked_objects"] == {
        "available": False,
        "scope": "disabled_in_normal_profile",
    }
    assert final["tracemalloc"]["available"] is False
    assert final["headless_visibility"]["tk_image_count"] is None
    assert final["headless_visibility"]["in_memory_history_count"] is None
    assert final["storage"]["history_file"]["record_count"] is None
    assert not recorder.trace_baseline_path.exists()
    assert recorder.artifacts == [str(recorder.samples_path)]


def test_detailed_checkpoint_writes_bounded_baseline_and_final_traces(
    monkeypatch: Any, tmp_path: Path
) -> None:
    _isolate_application_data(monkeypatch, tmp_path)
    run_root = tmp_path / "run"
    (run_root / "tmp").mkdir(parents=True)
    recorder = LifecycleCheckpointRecorder(run_root, jobs=1, detailed=True)
    retained: list[dict[str, int]] = []
    try:
        recorder.start()
        recorder.before_job(1)
        retained.extend({"index": index} for index in range(100))
        final = recorder.after_job(1, extra={"case_id": "one"})
    finally:
        recorder.finish()

    assert retained
    assert recorder.trace_baseline_path.is_file()
    assert recorder.trace_final_path.is_file()
    assert final["gc_tracked_objects"]["scope"] == "gc_tracked_objects_only"
    trace = final["tracemalloc"]
    assert trace["available"] is True
    assert trace["scope"] == "python_allocations_visible_to_tracemalloc"
    assert trace["baseline_delta"] is not None
    assert len(trace["baseline_delta"]["top_positive_locations"]) <= 20


def test_soak_releases_full_result_before_checkpoint_and_reuses_source(
    monkeypatch: Any, tmp_path: Path
) -> None:
    observed_urls: list[str] = []
    result_sentinels: list[weakref.ReferenceType[object]] = []

    class ResultSentinel:
        pass

    class FakeRunner:
        run_root = tmp_path

        def run_job(self, **kwargs: Any) -> dict[str, Any]:
            observed_urls.append(str(kwargs["url"]))
            sentinel = ResultSentinel()
            result_sentinels.append(weakref.ref(sentinel))
            output_dir = tmp_path / str(kwargs["case_id"]) / "output"
            return {
                "case_id": kwargs["case_id"],
                "duration_seconds": 0.1,
                "error": None,
                "media_output_count": 1,
                "staging_entries_after": [],
                "resource_metrics": {
                    "peak_zombie_processes": 0,
                    "peak_child_processes": 1,
                },
                "active_children_before_harness_cleanup": [],
                "events": [{"kind": "history_record"}],
                "job": {"output_dir": str(output_dir)},
                "large_unneeded_result_owner": sentinel,
            }

    class FakeServer:
        def url(self, path: str) -> str:
            return f"http://fixture.invalid{path}"

    class FakeRecorder:
        def __init__(self, run_root: Path, *, jobs: int, detailed: bool) -> None:
            self.samples_path = run_root / "samples.jsonl"
            self.samples_path.write_text("", encoding="utf-8")
            self.artifacts = [str(self.samples_path)]
            self._rss = 100

        def start(self) -> dict[str, Any]:
            return {"process": {"rss_bytes": self._rss, "fd_or_handle_count": 5}}

        def before_job(self, job_index: int) -> dict[str, Any]:
            return {"job_index": job_index}

        def after_job(self, job_index: int, *, extra: dict[str, Any]) -> dict[str, Any]:
            gc.collect()
            assert result_sentinels[-1]() is None
            self._rss += 10
            sample = {
                "process": {
                    "rss_bytes": self._rss,
                    "fd_or_handle_count": 5,
                    "os_thread_count": 2,
                },
                "tracemalloc": {"current_bytes": None},
                "storage": {
                    "thumbnail_cache": {"file_count": 1, "bytes": 10},
                    "history_file": {
                        "record_count": None,
                        "visibility": "on_disk_only_ui_event_queue_not_pumped",
                    },
                },
            }
            with self.samples_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(sample) + "\n")
            return sample

        def finish(self) -> None:
            return

    monkeypatch.setattr(scenarios_module, "LifecycleCheckpointRecorder", FakeRecorder)
    scenario, findings = scenarios_module.lifecycle_soak(
        cast(Any, FakeRunner()),
        cast(Any, FakeServer()),
        jobs=2,
        detailed=False,
    )

    assert findings == []
    assert scenario["status"] == "passed"
    assert len(set(observed_urls)) == 1
    assert observed_urls == [
        "http://fixture.invalid/page/unicode?soak=controlled",
        "http://fixture.invalid/page/unicode?soak=controlled",
    ]
    assert all(reference() is None for reference in result_sentinels)
    assert (
        scenario["workload"]["full_pipeline_results_retained_during_sampling"] is False
    )
    assert scenario["metrics"]["headless_tk_image_count"] is None
    assert scenario["metrics"]["headless_in_memory_history_count"] is None


def test_cli_keeps_normal_soak_bounded_and_deep_supports_50_or_100() -> None:
    parser = _parser()

    normal = parser.parse_args(["normal"])
    deep = parser.parse_args(["deep"])
    extended = parser.parse_args(["deep", "--soak-jobs", "100"])

    assert not hasattr(normal, "soak_jobs")
    assert deep.soak_jobs == 50
    assert extended.soak_jobs == 100
