from __future__ import annotations

import queue
from pathlib import Path
from typing import Any
from unittest.mock import patch


def batch_failure_report_reset_probe(
    case_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    import yt_downloader.app as app_module
    from yt_downloader.app import (
        DownloaderApp,
        DownloadJob,
        DownloadOutcome,
        ExportMode,
        ManualExportSettings,
        Mp3ExportSettings,
        OutputType,
    )

    case_dir.mkdir(parents=True, exist_ok=True)
    report = case_dir / "batch-url-failures.txt"
    old_contents = "failure from the previous batch\n"
    report.write_text(old_contents, encoding="utf-8")
    processed: list[str] = []
    app = DownloaderApp.__new__(DownloaderApp)
    app.events = queue.Queue()
    app.cancel_requested = False
    app._active_progress_context = None
    app._download_worker_single = lambda job, **_kwargs: (
        processed.append(job.url) or DownloadOutcome(success_count=1)
    )
    job = DownloadJob(
        url="https://www.youtube.com/watch?v=one",
        urls=[
            "https://www.youtube.com/watch?v=one",
            "https://www.youtube.com/watch?v=two",
        ],
        output_dir=case_dir / "output",
        output_type=OutputType.MP4,
        quality_label="360p",
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        embed_metadata=False,
        write_info_json=False,
        tags=[],
    )
    original_unlink = Path.unlink

    def deny_report_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        if path == report:
            raise PermissionError("injected report lock")
        original_unlink(path, *args, **kwargs)

    prior_report_path = app_module.BATCH_FAILURE_REPORT_PATH
    try:
        app_module.BATCH_FAILURE_REPORT_PATH = report
        with patch.object(Path, "unlink", deny_report_unlink):
            app._download_worker(job)
    finally:
        app_module.BATCH_FAILURE_REPORT_PATH = prior_report_path

    errors = [payload for kind, payload in app.events.queue if kind == "error"]
    old_report_preserved = report.read_text(encoding="utf-8") == old_contents
    aborted_before_media = not processed
    understandable_error = (
        len(errors) == 1
        and "could not reset the batch failure report" in str(errors[0]).lower()
    )
    passed = old_report_preserved and aborted_before_media and understandable_error
    evidence = [
        f"Media worker calls after injected reset failure: {len(processed)}",
        f"Previous report preserved without mixed new entries: {old_report_preserved}",
        f"One understandable terminal error emitted: {understandable_error}",
        f"Observed error: {errors[0] if errors else 'missing'}",
    ]
    scenario_id = "reliability.batch_failure_report_reset"
    scenario = {
        "id": scenario_id,
        "evidence_tier": "unit_static",
        "category": "reliability",
        "status": "passed" if passed else "failed",
        "duration_seconds": 0.0,
        "metrics": {
            "media_worker_calls_after_reset_failure": len(processed),
            "old_report_preserved": old_report_preserved,
            "understandable_error_emitted": understandable_error,
        },
        "evidence": evidence,
        "artifacts": [str(report)],
        "error": None,
    }
    if passed:
        return scenario, []
    return scenario, [
        {
            "id": "REL-BATCH-REPORT-RESET-001",
            "title": "A locked batch failure report can mix stale and current-run failures",
            "classification": "reliability defect",
            "severity": "medium",
            "area": "yt_downloader/app.py batch failure report lifecycle",
            "reproduction": [
                "Run ./engineering-quality/run normal --scenario reliability.batch_failure_report_reset.",
                "Leave a prior batch report in place and inject an unlink permission failure.",
                "Require the batch to stop before media work rather than append current failures to stale evidence.",
            ],
            "evidence": evidence,
            "suggested_fix": "Treat failure-report reset as a required batch initialization step and surface an understandable error before processing any URL.",
            "scenario_id": scenario_id,
        }
    ]
