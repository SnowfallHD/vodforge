from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Any

from .fault_server import FixtureHTTPServer
from .maintainability import change_surface_probe
from .metrics import LifecycleCheckpointRecorder, lifecycle_growth_summary
from .mutation import run_bounded_mutation_campaign
from .pipeline import (
    HeadlessPipelineRunner,
    TracingQueue,
    active_child_snapshot,
    build_job,
    make_headless_app,
)
from .reliability import batch_failure_report_reset_probe
from .reliability_static import activity_log_failure_receipt_probe
from .security import (
    fresh_output_contract_probe,
    path_and_subprocess_probe,
    symlink_and_temp_probe,
    thumbnail_network_authority_probe,
    url_secret_persistence_probe,
)
from .static_analysis import run_static_suite

_LIFECYCLE_WORKER_OBJECT_TYPES = (
    "yt_dlp.YoutubeDL.YoutubeDL",
    "yt_downloader.models.DownloadJob",
)


def _selected_worker_object_counts(
    sample: dict[str, Any],
) -> dict[str, int | None]:
    selected = (sample.get("gc_tracked_objects") or {}).get(
        "selected_type_counts"
    ) or {}
    return {
        object_type: (
            selected.get(object_type)
            if type(selected.get(object_type)) is int
            else None
        )
        for object_type in _LIFECYCLE_WORKER_OBJECT_TYPES
    }


def _worker_object_retention_receipt(
    baseline: dict[str, Any], final_sample: dict[str, Any]
) -> tuple[
    dict[str, int | None],
    dict[str, int | None],
    dict[str, int | None],
    dict[str, int],
    bool | None,
]:
    before = _selected_worker_object_counts(baseline)
    after = _selected_worker_object_counts(final_sample)
    deltas = {
        object_type: (
            after[object_type] - before[object_type]
            if before[object_type] is not None and after[object_type] is not None
            else None
        )
        for object_type in _LIFECYCLE_WORKER_OBJECT_TYPES
    }
    positive = {
        object_type: delta
        for object_type, delta in deltas.items()
        if delta is not None and delta > 0
    }
    if positive:
        signal: bool | None = True
    elif all(delta is not None for delta in deltas.values()):
        signal = False
    else:
        signal = None
    return before, after, deltas, positive, signal


def _media_streams(
    result: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    media = [
        entry
        for entry in result.get("outputs", [])
        if Path(entry.get("path", "")).suffix.lower() in {".mp4", ".mp3"}
    ]
    streams = [
        stream
        for entry in media
        for stream in ((entry.get("ffprobe") or {}).get("streams") or [])
        if isinstance(stream, dict)
    ]
    return media, streams


def _scenario_from_pipeline(
    *,
    scenario_id: str,
    category: str,
    result: dict[str, Any],
    passed: bool,
    evidence: list[str],
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resources = result.get("resource_metrics") or {}
    job_completed = int(
        result.get("error") is None and int(result.get("media_output_count") or 0) > 0
    )
    job_cancelled = int(bool(result.get("cancel_requested")) and not job_completed)
    job_failed = int(not job_completed and not job_cancelled)
    live_children = [
        item
        for item in result.get("active_children_before_harness_cleanup") or []
        if item.get("alive")
    ]
    combined_metrics = {
        "jobs_attempted": 1,
        "jobs_completed": job_completed,
        "jobs_failed": job_failed,
        "jobs_cancelled": job_cancelled,
        "job_duration_seconds": result.get("duration_seconds"),
        "job_initialization_seconds": result.get("job_initialization_seconds"),
        "output_bytes": result.get("output_bytes"),
        "media_output_count": result.get("media_output_count"),
        "effective_throughput_bytes_per_second": result.get(
            "effective_throughput_bytes_per_second"
        ),
        "peak_rss_bytes": resources.get("peak_rss_bytes"),
        "peak_cpu_percent": resources.get("peak_cpu_percent"),
        "peak_disk_bytes": resources.get("peak_disk_bytes"),
        "fd_delta": resources.get("fd_delta"),
        "thread_delta": resources.get("thread_delta"),
        "peak_child_processes": resources.get("peak_child_processes"),
        "peak_zombie_processes": resources.get("peak_zombie_processes"),
        "orphaned_child_processes": len(live_children),
        "harness_emergency_cleanup_used": bool(
            result.get("harness_emergency_cleanup_used")
        ),
        "staging_entries_after": len(result.get("staging_entries_after") or []),
        **(result.get("diagnostic_timings") or {}),
        **(metrics or {}),
    }
    return {
        "id": scenario_id,
        "evidence_tier": "headless_production_pipeline",
        "category": category,
        "status": "passed" if passed else "failed",
        "duration_seconds": float(result.get("duration_seconds") or 0),
        "metrics": combined_metrics,
        "evidence": evidence,
        "artifacts": [str(Path(entry["path"])) for entry in result.get("outputs", [])]
        + [result.get("diagnostics_path", "")],
        "error": result.get("error"),
        "raw_result": str(
            Path(result["job"]["output_dir"]).parent / "pipeline-result.json"
        ),
    }


def _worker_cleanup_is_clean(result: dict[str, Any]) -> bool:
    return not any(
        item.get("alive")
        for item in result.get("active_children_before_harness_cleanup") or []
    ) and not result.get("harness_emergency_cleanup_used")


def _finding_for_failed_scenario(
    scenario: dict[str, Any],
    title: str,
    classification: str,
    severity: str,
    area: str,
    fix: str,
) -> dict[str, Any]:
    return {
        "id": "HARNESS-"
        + scenario["id"].upper().replace(".", "-").replace("_", "-")[:70],
        "title": title,
        "classification": classification,
        "severity": severity,
        "area": area,
        "reproduction": [
            f"Run ./engineering-quality/run normal --scenario {scenario['id']}",
            "Inspect the scenario evidence and raw pipeline result.",
        ],
        "evidence": scenario["evidence"]
        + ([f"Error: {scenario['error']}"] if scenario.get("error") else []),
        "suggested_fix": fix,
        "scenario_id": scenario["id"],
    }


def correctness_mp4(
    runner: HeadlessPipelineRunner, server: FixtureHTTPServer
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result = runner.run_job(
        case_id="correctness-local-mp4",
        url=server.url("/page/unicode"),
        output_type="MP4",
        embed_thumbnail=True,
    )
    media, streams = _media_streams(result)
    attached_art = [
        stream
        for stream in streams
        if stream.get("codec_type") == "video"
        and int((stream.get("disposition") or {}).get("attached_pic") or 0)
    ]
    video = [
        stream
        for stream in streams
        if stream.get("codec_type") == "video"
        and not int((stream.get("disposition") or {}).get("attached_pic") or 0)
    ]
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    metadata_files = [
        entry
        for entry in result["outputs"]
        if Path(entry["path"]).name == "metadata.json"
    ]
    thumbnail_files = [
        entry
        for entry in result["outputs"]
        if Path(entry["path"]).name == "thumbnail.jpeg"
    ]
    metadata_payload = (
        json.loads(Path(metadata_files[0]["path"]).read_text(encoding="utf-8"))
        if metadata_files
        else {}
    )
    metadata_text = json.dumps(metadata_payload, ensure_ascii=False)
    expected_tags = ["vodforge-quality", "synthetic-fixture", "unicode-Δ"]
    media_format = (media[0].get("ffprobe") or {}).get("format") if media else {}
    embedded_tags = media_format.get("tags") if isinstance(media_format, dict) else {}
    embedded_keywords = str((embedded_tags or {}).get("keywords") or "").casefold()
    embedded_metadata_valid = bool(
        str((embedded_tags or {}).get("title") or "").strip()
        and all(tag.casefold() in embedded_keywords for tag in expected_tags)
    )
    metadata_fields_valid = (
        "Δοκιμή_日本語" in str(metadata_payload.get("title") or "")
        and "Synthetic metadata-rich" in str(metadata_payload.get("description") or "")
        and metadata_payload.get("extra_tags") == expected_tags
        and bool(metadata_payload.get("thumbnail"))
    )
    stale_staging_reference = ".vfstage" in metadata_text
    output_root = Path(result["job"]["output_dir"]).resolve()
    organized_paths = [Path(entry["path"]).resolve() for entry in result["outputs"]]
    output_paths_contained = all(
        os.path.commonpath([str(output_root), str(path)]) == str(output_root)
        for path in organized_paths
    )
    descriptive_hierarchy = (
        bool(media) and "videos - no playlist" in Path(media[0]["path"]).parts
    )
    readable = bool(media) and all(entry.get("readable") for entry in media)
    core_passed = (
        result.get("error") is None
        and len(media) == 1
        and readable
        and any(str(stream.get("codec_name")).lower() == "h264" for stream in video)
        and any(str(stream.get("codec_name")).lower() == "aac" for stream in audio)
        and len(attached_art) == 1
        and embedded_metadata_valid
        and bool(metadata_files)
        and not result.get("staging_entries_after")
        and _worker_cleanup_is_clean(result)
        and metadata_fields_valid
        and output_paths_contained
        and descriptive_hierarchy
    )
    passed = core_passed and not stale_staging_reference
    evidence = [
        f"Real worker entrypoint: {result['pipeline_entrypoint']}",
        f"Committed media outputs: {len(media)}; independently ffprobe-readable: {readable}",
        f"Video codecs: {[stream.get('codec_name') for stream in video]}",
        f"Audio codecs: {[stream.get('codec_name') for stream in audio]}",
        f"Requested embedded thumbnail; attached-picture streams committed: {len(attached_art)}",
        f"Embedded title and requested keyword tags retained: {embedded_metadata_valid}",
        f"Compact metadata sidecars: {len(metadata_files)}; separate thumbnails: {len(thumbnail_files)}",
        f"Metadata title/description/tags/thumbnail fields valid: {metadata_fields_valid}",
        f"Output hierarchy contained and descriptive: {output_paths_contained and descriptive_hierarchy}",
        f"Metadata contains stale .vfstage path reference: {stale_staging_reference}",
        f"Staging entries after completion: {result.get('staging_entries_after')}",
    ]
    scenario = _scenario_from_pipeline(
        scenario_id="correctness.local_mp4_real_pipeline",
        category="correctness",
        result=result,
        passed=passed,
        evidence=evidence,
        metrics={
            "metadata_sidecar_count": len(metadata_files),
            "thumbnail_sidecar_count": len(thumbnail_files),
            "metadata_fields_valid": metadata_fields_valid,
            "attached_picture_streams": len(attached_art),
            "embedded_metadata_valid": embedded_metadata_valid,
            "stale_staging_metadata_references": int(stale_staging_reference),
            "output_paths_contained": output_paths_contained,
            "descriptive_hierarchy": descriptive_hierarchy,
        },
    )
    if stale_staging_reference and core_passed:
        findings = [
            {
                "id": "CORR-METADATA-STAGE-PATH-001",
                "title": "Committed metadata sidecar preserves a stale private staging path",
                "classification": "correctness defect",
                "severity": "low",
                "area": "yt_downloader/app.py compact metadata sidecar packaging",
                "reproduction": [
                    "Run ./engineering-quality/run normal --scenario correctness.local_mp4_real_pipeline.",
                    "Open the committed metadata.json and inspect best_thumbnail.filepath after .vfstage cleanup.",
                ],
                "evidence": [
                    f"Committed metadata: {metadata_files[0]['path']}",
                    "The JSON contains .vfstage even though the run staging directory no longer exists.",
                ],
                "suggested_fix": "Remove private staging file paths from the compact sidecar or rewrite them to the committed thumbnail path before atomic packaging.",
                "scenario_id": scenario["id"],
            }
        ]
    elif passed:
        findings = []
    else:
        findings = [
            _finding_for_failed_scenario(
                scenario,
                "Generated legal MP4 fixture did not satisfy the complete production-pipeline contract",
                "correctness defect",
                "high",
                "real yt-dlp/FFmpeg/ffprobe pipeline",
                "Use the raw diagnostic stage that failed; repair production selection, transcode, validation, sidecar, or commit behavior without adding a parallel harness implementation.",
            )
        ]
    return scenario, findings


def lifecycle_quit_restart_recovery(
    runner: HeadlessPipelineRunner,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Exercise durable settings, run, process, and staging owners across restart."""

    from yt_downloader.process_lifecycle import process_command, terminate_pid
    from yt_downloader.run_state import ActiveRunStore, recover_interrupted_run
    from yt_downloader.safe_output import create_private_staging_directory
    from yt_downloader.settings_store import load_settings, save_settings

    case_root = runner.run_root / "cases" / "lifecycle-quit-restart-recovery"
    output_dir = case_root / "selected-output"
    state_dir = case_root / "application-state"
    settings_path = state_dir / "settings.json"
    run_state_path = state_dir / "active-run.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    save_settings(
        settings_path,
        {
            "output_dir": str(output_dir),
            "output_type": "MP3",
            "quality": "720p HD",
        },
    )
    settings_after_restart = load_settings(settings_path)

    job = build_job(
        url="https://example.invalid/generated",
        output_dir=output_dir,
        output_type="MP4",
    )
    job.run_id = "hard-exit-run"
    first_queued = build_job(
        url="https://example.invalid/generated-queued-first",
        output_dir=output_dir,
        output_type="MP4",
    )
    first_queued.run_id = "queued-first"
    second_queued = build_job(
        url="https://example.invalid/generated-queued-second",
        output_dir=output_dir,
        output_type="MP3",
    )
    second_queued.run_id = "queued-second"
    store = ActiveRunStore(run_state_path)
    store.begin(job, [first_queued, second_queued])
    stage = create_private_staging_directory(output_dir)
    partial = stage / "interrupted-source.part"
    partial.write_bytes(b"generated partial media" * 1024)
    store.add_staging_dir(job.run_id, stage)
    tail = Path("/usr/bin/tail")
    child_command = (
        [str(tail), "-f", str(partial)]
        if tail.is_file()
        else [sys.executable, "-c", "import time; time.sleep(120)", str(partial)]
    )
    orphan_launcher = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import subprocess,sys; "
                "p=subprocess.Popen(sys.argv[1:], start_new_session=True, "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL); print(p.pid)"
            ),
            *child_command,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    child_pid = int(orphan_launcher.stdout.strip())
    store.child_started(child_pid, child_command)
    trace = [
        {
            "phase": "active_before_restart_recovery",
            "stage_exists": stage.is_dir(),
            "partial_size": partial.stat().st_size,
            "child_pid": child_pid,
            "child_command": process_command(child_pid),
            "run_state": store.load(),
        }
    ]
    recovered = []
    recovery_error: str | None = None
    try:
        recovered = recover_interrupted_run(store)
    except Exception as exc:  # noqa: BLE001 - retain cleanup evidence
        recovery_error = f"{type(exc).__name__}: {exc}"
    finally:
        if process_command(child_pid) is not None:
            terminate_pid(child_pid)
    child_reaped = process_command(child_pid) is None
    trace.append(
        {
            "phase": "after_restart_recovery",
            "stage_exists": stage.exists(),
            "staging_root_exists": (output_dir / ".vfstage").exists(),
            "child_alive": not child_reaped,
            "run_state": store.load(),
            "recovery_error": recovery_error,
        }
    )
    queued_after_restart = store.load_queued_jobs()
    store.begin(first_queued, [second_queued])
    store.clear(first_queued.run_id)
    store.begin(second_queued, [])
    store.clear(second_queued.run_id)
    durable_failed_jobs = store.load_failed_jobs()
    store.clear(job.run_id)
    trace.append(
        {
            "phase": "after_library_removal",
            "run_state_exists": run_state_path.exists(),
            "staging_root_exists": (output_dir / ".vfstage").exists(),
            "recovered_queue_order": [
                queued_job.run_id for queued_job in queued_after_restart
            ],
        }
    )
    trace_path = case_root / "quit-restart-trace.json"
    trace_path.write_text(
        json.dumps({"snapshots": trace}, indent=2) + "\n", encoding="utf-8"
    )
    settings_private = (settings_path.stat().st_mode & 0o777) == 0o600
    settings_preserved = settings_after_restart == {
        "output_dir": str(output_dir),
        "output_type": "MP3",
        "quality": "720p HD",
    }
    failed_preserved = (
        len(recovered) == 1
        and recovered[0].terminal_status == "Failed"
        and [item.run_id for item in durable_failed_jobs] == [job.run_id]
    )
    queue_preserved = [queued_job.run_id for queued_job in queued_after_restart] == [
        "queued-first",
        "queued-second",
    ]
    stage_cleaned = not stage.exists() and not (output_dir / ".vfstage").exists()
    journal_removed = not run_state_path.exists()
    passed = bool(
        recovery_error is None
        and settings_preserved
        and settings_private
        and failed_preserved
        and queue_preserved
        and child_reaped
        and stage_cleaned
        and journal_removed
    )
    scenario = {
        "id": "lifecycle.quit_restart_recovery",
        "evidence_tier": "headless_production_pipeline",
        "category": "lifecycle",
        "status": "passed" if passed else "failed",
        "duration_seconds": 0.0,
        "metrics": {
            "jobs_attempted": 1,
            "jobs_completed": 0,
            "jobs_failed": int(failed_preserved),
            "jobs_cancelled": 0,
            "settings_persisted": settings_preserved,
            "settings_private": settings_private,
            "orphan_child_reaped": child_reaped,
            "recorded_stage_cleaned": stage_cleaned,
            "failed_state_durable_until_removal": failed_preserved,
            "queued_runs_preserved_in_order": queue_preserved,
            "journal_removed_by_library_removal": journal_removed,
        },
        "evidence": [
            f"Restart loaded the selected output root and export preferences unchanged: {settings_preserved}",
            f"The persisted settings file was private 0600: {settings_private}",
            f"Recovery reaped the exact recorded child and removed its staging transaction: {child_reaped and stage_cleaned}",
            f"The interrupted run used Failed and survived a later run until removal: {failed_preserved}",
            f"Two queued runs survived restart in their original order and promoted exactly once: {queue_preserved}",
            f"Library removal cleared the durable failure journal: {journal_removed}",
        ],
        "artifacts": [str(trace_path), str(settings_path)],
        "error": recovery_error,
    }
    findings = (
        []
        if passed
        else [
            _finding_for_failed_scenario(
                scenario,
                "Quit/restart recovery violated an ownership or cleanup contract",
                "reliability defect",
                "high",
                "settings_store, run_state, process_lifecycle, and safe_output",
                "Keep settings, active-run journaling, child reaping, and recorded staging cleanup independently durable and fail closed on uncertain ownership.",
            )
        ]
    )
    return scenario, findings


def _audio_bitrate_kbps(streams: list[dict[str, Any]]) -> float | None:
    values = []
    for stream in streams:
        if stream.get("codec_type") != "audio":
            continue
        try:
            values.append(float(stream.get("bit_rate")) / 1000.0)
        except (TypeError, ValueError):
            continue
    return max(values) if values else None


def correctness_mp4_embedding_disabled(
    runner: HeadlessPipelineRunner, server: FixtureHTTPServer
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result = runner.run_job(
        case_id="correctness-local-mp4-embedding-disabled",
        url=server.url("/page/unicode"),
        output_type="MP4",
        embed_metadata=False,
        embed_thumbnail=False,
        write_thumbnail=False,
        write_info_json=False,
    )
    media, streams = _media_streams(result)
    attached_art = [
        stream
        for stream in streams
        if stream.get("codec_type") == "video"
        and int((stream.get("disposition") or {}).get("attached_pic") or 0)
    ]
    format_data = (media[0].get("ffprobe") or {}).get("format") if media else {}
    raw_tags = format_data.get("tags") if isinstance(format_data, dict) else {}
    embedded_tag_keys = {
        str(key).casefold() for key in raw_tags if isinstance(raw_tags, dict)
    }
    user_metadata_keys = {
        "title",
        "artist",
        "album",
        "album_artist",
        "comment",
        "description",
        "synopsis",
        "keywords",
    }
    embedded_user_metadata = sorted(embedded_tag_keys & user_metadata_keys)
    passed = (
        result.get("error") is None
        and len(media) == 1
        and all(entry.get("readable") for entry in media)
        and not attached_art
        and not embedded_user_metadata
        and not result.get("staging_entries_after")
        and _worker_cleanup_is_clean(result)
    )
    scenario = _scenario_from_pipeline(
        scenario_id="correctness.local_mp4_embedding_disabled",
        category="correctness",
        result=result,
        passed=passed,
        evidence=[
            "Drove the real worker with MP4 metadata and thumbnail embedding disabled.",
            f"Committed attached-picture streams: {len(attached_art)}",
            f"Committed user metadata keys: {embedded_user_metadata}",
            f"Readable committed media outputs: {sum(bool(entry.get('readable')) for entry in media)}",
            f"Staging entries after completion: {result.get('staging_entries_after')}",
        ],
        metrics={
            "attached_picture_streams": len(attached_art),
            "embedded_user_metadata_keys": embedded_user_metadata,
        },
    )
    findings = (
        []
        if passed
        else [
            _finding_for_failed_scenario(
                scenario,
                "Metadata-disabled MP4 did not honor its output contract",
                "correctness defect",
                "medium",
                "MP4 FFmpeg transcode and fresh-output validation",
                "Make the production transcode explicitly drop metadata/artwork when disabled and keep the fresh validator fail-closed.",
            )
        ]
    )
    return scenario, findings


def correctness_mp3(
    runner: HeadlessPipelineRunner, server: FixtureHTTPServer
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    requested = 192
    result = runner.run_job(
        case_id="correctness-local-mp3",
        url=server.url("/page/unicode"),
        output_type="MP3",
        mp3_bitrate_kbps=requested,
    )
    media, streams = _media_streams(result)
    bitrate = _audio_bitrate_kbps(streams)
    attached_art = [
        stream
        for stream in streams
        if stream.get("codec_type") == "video"
        and int((stream.get("disposition") or {}).get("attached_pic") or 0)
    ]
    format_data = (media[0].get("ffprobe") or {}).get("format") if media else {}
    raw_tags = format_data.get("tags") if isinstance(format_data, dict) else {}
    expected_tags = ["vodforge-quality", "synthetic-fixture", "unicode-Δ"]
    keywords = str((raw_tags or {}).get("keywords") or "").casefold()
    embedded_metadata_valid = bool(
        str((raw_tags or {}).get("title") or "").strip()
        and all(tag.casefold() in keywords for tag in expected_tags)
    )
    bitrate_matches = (
        bitrate is not None and requested * 0.85 <= bitrate <= requested * 1.15
    )
    metadata_files = [
        entry
        for entry in result["outputs"]
        if Path(entry["path"]).name == "metadata.json"
    ]
    passed = (
        result.get("error") is None
        and len(media) == 1
        and all(entry.get("readable") for entry in media)
        and any(str(stream.get("codec_name")).lower() == "mp3" for stream in streams)
        and bitrate_matches
        and len(attached_art) == 1
        and embedded_metadata_valid
        and bool(metadata_files)
        and not result.get("staging_entries_after")
        and _worker_cleanup_is_clean(result)
    )
    evidence = [
        f"Requested MP3 bitrate: {requested} kbps; independent ffprobe stream bitrate: {bitrate} kbps",
        f"Bitrate within ±15%: {bitrate_matches}",
        f"Requested embedded cover; attached-picture streams committed: {len(attached_art)}",
        f"Embedded title and requested keyword tags retained: {embedded_metadata_valid}",
        f"Committed media outputs: {len(media)}; metadata sidecars: {len(metadata_files)}",
        f"Staging entries after completion: {result.get('staging_entries_after')}",
    ]
    scenario = _scenario_from_pipeline(
        scenario_id="correctness.local_mp3_bitrate_real_pipeline",
        category="correctness",
        result=result,
        passed=passed,
        evidence=evidence,
        metrics={
            "requested_mp3_bitrate_kbps": requested,
            "observed_mp3_bitrate_kbps": bitrate,
            "bitrate_matches": bitrate_matches,
            "attached_picture_streams": len(attached_art),
            "embedded_metadata_valid": embedded_metadata_valid,
        },
    )
    findings = (
        []
        if passed
        else [
            _finding_for_failed_scenario(
                scenario,
                "Generated legal MP3 fixture did not match the requested output contract",
                "correctness defect",
                "high",
                "MP3 production pipeline and fresh-output validation",
                "Make the real encoder and pre-commit validation enforce the requested MP3 bitrate, then retain independent ffprobe verification in the harness.",
            )
        ]
    )
    return scenario, findings


def correctness_source_quality(
    runner: HeadlessPipelineRunner,
    server: FixtureHTTPServer,
    *,
    requested_label: str,
    expected_source_height: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    slug = requested_label.lower().replace(" ", "-")
    result = runner.run_job(
        case_id=f"correctness-source-quality-{slug}",
        url=server.url(f"/page/multi?quality={slug}"),
        output_type="MP4",
        quality_label=requested_label,
        write_thumbnail=False,
        write_info_json=False,
    )
    metadata = result.get("latest_metadata") or {}
    formats = [item for item in metadata.get("formats") or [] if isinstance(item, dict)]
    offered_heights = sorted(
        {
            int(item["height"])
            for item in formats
            if isinstance(item.get("height"), (int, float))
        }
    )
    source_height = metadata.get("height")
    media, streams = _media_streams(result)
    output_video = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), {}
    )
    output_height = output_video.get("height")
    passed = (
        result.get("error") is None
        and offered_heights == [360, 540]
        and source_height == expected_source_height
        and output_height == expected_source_height
        and len(media) == 1
        and all(item.get("readable") for item in media)
        and not result.get("staging_entries_after")
        and _worker_cleanup_is_clean(result)
    )
    scenario = _scenario_from_pipeline(
        scenario_id=f"correctness.source_quality_selection_{slug}",
        category="correctness",
        result=result,
        passed=passed,
        evidence=[
            f"Requested quality cap: {requested_label}; source inventory heights captured this run: {offered_heights}",
            f"Production-selected source height/format: {source_height} / {metadata.get('format_id')}",
            f"Generated final-output height (separate from source evidence): {output_height}",
            f"Validated committed media: {len(media)}; staging residue: {result.get('staging_entries_after')}",
        ],
        metrics={
            "requested_quality_label": requested_label,
            "source_inventory_heights": offered_heights,
            "selected_source_height": source_height,
            "generated_output_height": output_height,
        },
    )
    return scenario, [] if passed else [
        _finding_for_failed_scenario(
            scenario,
            "Source quality selection did not choose the best eligible format from the captured inventory",
            "correctness defect",
            "high",
            "source format selection and MP4 export planning",
            "Keep one canonical selection algorithm, compare against the same-run provider inventory, and preserve source properties separately from generated-output properties.",
        )
    ]


def reliability_http_failure(
    runner: HeadlessPipelineRunner, server: FixtureHTTPServer
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result = runner.run_job(
        case_id="reliability-http-404", url=server.url("/status/404"), output_type="MP4"
    )
    resources = result.get("resource_metrics") or {}
    passed = (
        bool(result.get("error"))
        and result.get("media_output_count") == 0
        and not result.get("staging_entries_after")
        and not resources.get("peak_zombie_processes")
        and _worker_cleanup_is_clean(result)
    )
    evidence = [
        f"Provider error surfaced: {result.get('error')}",
        f"Committed media outputs: {result.get('media_output_count')}",
        f"Staging entries after failure: {result.get('staging_entries_after')}",
        f"Peak zombie processes: {resources.get('peak_zombie_processes')}",
    ]
    scenario = _scenario_from_pipeline(
        scenario_id="reliability.http_404_cleanup",
        category="reliability",
        result=result,
        passed=passed,
        evidence=evidence,
    )
    findings = (
        []
        if passed
        else [
            _finding_for_failed_scenario(
                scenario,
                "HTTP failure left an unclear outcome or incomplete state",
                "reliability defect",
                "medium",
                "source analysis/download failure cleanup",
                "Preserve the provider error while guaranteeing no final commit, stage residue, or owned child remains.",
            )
        ]
    )
    return scenario, findings


def reliability_retry(
    runner: HeadlessPipelineRunner, server: FixtureHTTPServer
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    before = server.state.snapshot()
    result = runner.run_job(
        case_id="reliability-retry-503",
        url=server.url("/fault/retry/page"),
        output_type="MP3",
    )
    after = server.state.snapshot()
    failures = int(after["statuses"].get("503", 0)) - int(
        before["statuses"].get("503", 0)
    )
    diagnostics = str(result.get("diagnostic_excerpt") or "")
    retry_receipts = [
        line
        for line in diagnostics.splitlines()
        if "source analysis transient network failure on attempt" in line
        and "retrying attempt" in line
    ]
    passed = (
        failures >= 2
        and len(retry_receipts) >= 2
        and result.get("error") is None
        and result.get("media_output_count") == 1
        and not result.get("staging_entries_after")
        and _worker_cleanup_is_clean(result)
    )
    evidence = [
        f"Injected HTTP 503 responses observed: {failures}",
        f"Observable bounded source-analysis retry receipts: {len(retry_receipts)}",
        *(retry_receipts[:3] or ["No source-analysis retry receipt was recorded"]),
        f"Final pipeline error: {result.get('error')}",
        f"Validated media output count: {result.get('media_output_count')}",
        f"Staging entries after retry case: {result.get('staging_entries_after')}",
    ]
    scenario = _scenario_from_pipeline(
        scenario_id="reliability.transient_http_retry",
        category="reliability",
        result=result,
        passed=passed,
        evidence=evidence,
        metrics={
            "injected_503_responses": failures,
            "source_analysis_retry_receipts": len(retry_receipts),
        },
    )
    findings = (
        []
        if passed
        else [
            _finding_for_failed_scenario(
                scenario,
                "Configured transient HTTP retries did not recover cleanly",
                "reliability defect",
                "medium",
                "yt-dlp source analysis and retry configuration",
                "Apply bounded retry/backoff consistently to source analysis and download, and report attempts in the event contract.",
            )
        ]
    )
    return scenario, findings


def reliability_cancel(
    runner: HeadlessPipelineRunner, server: FixtureHTTPServer
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    first_downloading: list[float | None] = [None]
    cancellation_requested_at: list[float | None] = [None]

    def cancel_when(events: Any, _app: Any) -> bool:
        observed = any(
            event.get("kind") == "status"
            and "downloading" in str(event.get("payload", "")).lower()
            for event in events.trace
        )
        if observed and first_downloading[0] is None:
            first_downloading[0] = time.monotonic()
        should_cancel = (
            first_downloading[0] is not None
            and time.monotonic() - first_downloading[0] >= 0.25
        )
        if should_cancel and cancellation_requested_at[0] is None:
            cancellation_requested_at[0] = time.monotonic()
        return should_cancel

    result = runner.run_job(
        case_id="reliability-cancel-slow",
        url=server.url("/slow/page"),
        output_type="MP4",
        cancel_when=cancel_when,
        cancel_timeout_seconds=20,
    )
    resources = result.get("resource_metrics") or {}
    cleanup_latency = (
        time.monotonic() - cancellation_requested_at[0]
        if cancellation_requested_at[0] is not None
        else None
    )
    cancelled_text = "cancel" in str(result.get("error") or "").lower() or any(
        event.get("kind") == "stopped" and "cancel" in str(event.get("payload")).lower()
        for event in result.get("events", [])
    )
    passed = (
        result.get("cancel_requested")
        and cancelled_text
        and result.get("media_output_count") == 0
        and not result.get("staging_entries_after")
        and not resources.get("peak_zombie_processes")
        and _worker_cleanup_is_clean(result)
    )
    evidence = [
        f"Cancellation flag set after real download began: {result.get('cancel_requested') and first_downloading[0] is not None}",
        f"Cancellation outcome was understandable: {cancelled_text}; error={result.get('error')}",
        f"Committed media outputs: {result.get('media_output_count')}",
        f"Staging residue: {result.get('staging_entries_after')}",
        f"Peak zombie processes: {resources.get('peak_zombie_processes')}",
    ]
    scenario = _scenario_from_pipeline(
        scenario_id="reliability.cancel_during_slow_download",
        category="reliability",
        result=result,
        passed=passed,
        evidence=evidence,
        metrics={"cancellation_to_clean_return_seconds": cleanup_latency},
    )
    findings = (
        []
        if passed
        else [
            _finding_for_failed_scenario(
                scenario,
                "Cancellation during a real slow transfer was not clean",
                "reliability defect",
                "high",
                "worker cancellation, staging cleanup, and child lifecycle",
                "Ensure cancel reaches source analysis/download/FFmpeg, reap owned children, remove the run stage, and emit one truthful stopped state.",
            )
        ]
    )
    return scenario, findings


def reliability_cancel_transcode(
    runner: HeadlessPipelineRunner,
    server: FixtureHTTPServer,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    transcode_seen_at: list[float | None] = [None]
    cancellation_requested_at: list[float | None] = [None]

    def cancel_when(events: Any, _app: Any) -> bool:
        observed = any(
            event.get("kind") == "status"
            and "transcoding" in str(event.get("payload", "")).lower()
            for event in events.trace
        )
        if observed and transcode_seen_at[0] is None:
            transcode_seen_at[0] = time.monotonic()
        should_cancel = (
            transcode_seen_at[0] is not None
            and time.monotonic() - transcode_seen_at[0] >= 0.15
        )
        if should_cancel and cancellation_requested_at[0] is None:
            cancellation_requested_at[0] = time.monotonic()
        return should_cancel

    result = runner.run_job(
        case_id="reliability-cancel-transcode",
        url=server.url("/page/long"),
        output_type="MP4",
        cancel_when=cancel_when,
        cancel_timeout_seconds=30,
    )
    cleanup_latency = (
        time.monotonic() - cancellation_requested_at[0]
        if cancellation_requested_at[0] is not None
        else None
    )
    cancelled_text = "cancel" in str(result.get("error") or "").lower() or any(
        event.get("kind") == "stopped" and "cancel" in str(event.get("payload")).lower()
        for event in result.get("events", [])
    )
    passed = (
        transcode_seen_at[0] is not None
        and result.get("cancel_requested")
        and cancelled_text
        and result.get("media_output_count") == 0
        and not result.get("staging_entries_after")
        and _worker_cleanup_is_clean(result)
    )
    scenario = _scenario_from_pipeline(
        scenario_id="reliability.cancel_during_transcode",
        category="reliability",
        result=result,
        passed=passed,
        evidence=[
            f"Real transcode status observed before cancellation: {transcode_seen_at[0] is not None}",
            f"Cancellation outcome was understandable: {cancelled_text}; error={result.get('error')}",
            f"Cancellation-to-clean-return latency: {cleanup_latency}",
            f"Committed outputs: {result.get('media_output_count')}; staging residue: {result.get('staging_entries_after')}",
            f"Production child survivors: {result.get('active_children_before_harness_cleanup')}",
        ],
        metrics={"cancellation_to_clean_return_seconds": cleanup_latency},
    )
    return scenario, [] if passed else [
        _finding_for_failed_scenario(
            scenario,
            "Cancellation during real FFmpeg transcoding was not clean",
            "reliability defect",
            "high",
            "FFmpeg cancellation, process reaping, and staging cleanup",
            "Make transcode cancellation terminate and reap the owned FFmpeg process, remove encoder sidecars and staging, and emit one truthful stopped state.",
        )
    ]


def reliability_interrupted_transfer(
    runner: HeadlessPipelineRunner,
    server: FixtureHTTPServer,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    before = server.state.snapshot()
    result = runner.run_job(
        case_id="reliability-interrupted-transfer",
        url=server.url("/fault/interrupt/page"),
        output_type="MP4",
    )
    after = server.state.snapshot()
    interruptions = int(after.get("interruptions_injected", 0)) - int(
        before.get("interruptions_injected", 0)
    )
    passed = (
        interruptions >= 1
        and result.get("error") is None
        and result.get("media_output_count") == 1
        and not result.get("staging_entries_after")
        and _worker_cleanup_is_clean(result)
    )
    scenario = _scenario_from_pipeline(
        scenario_id="reliability.network_interruption_recovery",
        category="reliability",
        result=result,
        passed=passed,
        evidence=[
            f"Loopback TCP response interruptions injected: {interruptions}",
            f"Worker outcome after interruption: error={result.get('error')}",
            f"Validated committed media: {result.get('media_output_count')}",
            f"Staging residue: {result.get('staging_entries_after')}",
        ],
        metrics={
            "network_interruptions_injected": interruptions,
            "retry_recovered": passed,
        },
    )
    return scenario, [] if passed else [
        _finding_for_failed_scenario(
            scenario,
            "A single interrupted media response did not recover through the configured retry path",
            "reliability defect",
            "medium",
            "yt-dlp transfer retries and partial-file handling",
            "Use bounded resumable retries for interrupted transfers and preserve clean staging plus an understandable terminal error when recovery is exhausted.",
        )
    ]


def reliability_unwritable_output(
    runner: HeadlessPipelineRunner,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output_dir = runner.run_root / "cases" / "reliability-unwritable-output" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    original_mode = output_dir.stat().st_mode & 0o777
    output_dir.chmod(0o500)
    try:
        if os.access(output_dir, os.W_OK):
            scenario = {
                "id": "reliability.unwritable_output_directory",
                "evidence_tier": "headless_production_pipeline",
                "category": "reliability",
                "status": "skipped",
                "duration_seconds": 0.0,
                "metrics": {"jobs_attempted": 0, "simulation_supported": False},
                "evidence": [
                    "The current execution identity can still write a mode-0500 directory; the safe POSIX simulation is not valid on this runner."
                ],
                "artifacts": [str(output_dir)],
                "error": None,
            }
            return scenario, []
        result = runner.run_job(
            case_id="reliability-unwritable-output",
            url="http://127.0.0.1:9/not-reached",
            output_type="MP4",
            output_dir=output_dir,
        )
    finally:
        output_dir.chmod(original_mode)
    passed = (
        bool(result.get("error"))
        and result.get("media_output_count") == 0
        and not result.get("staging_entries_after")
        and _worker_cleanup_is_clean(result)
    )
    scenario = _scenario_from_pipeline(
        scenario_id="reliability.unwritable_output_directory",
        category="reliability",
        result=result,
        passed=passed,
        evidence=[
            f"Mode-0500 output preflight error: {result.get('error')}",
            f"No provider work or final output occurred: {result.get('media_output_count') == 0}",
            f"Staging residue: {result.get('staging_entries_after')}",
        ],
    )
    return scenario, [] if passed else [
        _finding_for_failed_scenario(
            scenario,
            "An unwritable output directory was not rejected cleanly before media work",
            "reliability defect",
            "high",
            "output-directory access preflight",
            "Fail at submission with a clear permission error and leave no staging, child process, or committed media.",
        )
    ]


def reliability_ffmpeg_failure(
    runner: HeadlessPipelineRunner,
    server: FixtureHTTPServer,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result = runner.run_job(
        case_id="reliability-ffmpeg-child-failure",
        url=server.url("/page/unicode"),
        output_type="MP4",
        ffmpeg_override=sys.executable,
    )
    passed = (
        bool(result.get("error"))
        and result.get("media_output_count") == 0
        and not result.get("staging_entries_after")
        and _worker_cleanup_is_clean(result)
    )
    scenario = _scenario_from_pipeline(
        scenario_id="reliability.ffmpeg_child_failure",
        category="reliability",
        result=result,
        passed=passed,
        evidence=[
            f"Injected non-FFmpeg executable: {sys.executable}",
            f"Understandable child/dependency error: {result.get('error')}",
            f"Committed outputs: {result.get('media_output_count')}; staging residue: {result.get('staging_entries_after')}",
            f"Production child survivors: {result.get('active_children_before_harness_cleanup')}",
        ],
        metrics={"dependency_failure_injected": True},
    )
    return scenario, [] if passed else [
        _finding_for_failed_scenario(
            scenario,
            "Injected FFmpeg dependency failure did not terminate cleanly",
            "reliability defect",
            "high",
            "FFmpeg discovery/invocation and worker cleanup",
            "Surface the dependency/child exit failure, reap every owned process, and remove all staged and temporary output.",
        )
    ]


def reliability_malformed(
    runner: HeadlessPipelineRunner,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result = runner.run_job(
        case_id="reliability-malformed-url", url="not a URL://[]", output_type="MP4"
    )
    passed = (
        bool(result.get("error"))
        and result.get("media_output_count") == 0
        and not result.get("staging_entries_after")
        and _worker_cleanup_is_clean(result)
    )
    scenario = _scenario_from_pipeline(
        scenario_id="reliability.malformed_url",
        category="reliability",
        result=result,
        passed=passed,
        evidence=[
            f"Malformed URL error: {result.get('error')}",
            f"Committed outputs: {result.get('media_output_count')}",
            f"Staging residue: {result.get('staging_entries_after')}",
        ],
    )
    return scenario, [] if passed else [
        _finding_for_failed_scenario(
            scenario,
            "Malformed URL handling was not clean",
            "reliability defect",
            "medium",
            "URL validation and source analysis",
            "Reject malformed schemes/hosts before media work and preserve a human-readable error without state mutation.",
        )
    ]


def lifecycle_staging_transitions(
    runner: HeadlessPipelineRunner,
    server: FixtureHTTPServer,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Observe staging ownership through skip, successor, completion, and removal."""

    from yt_downloader.app import create_staging_dir
    from yt_downloader.library_state import resolve_library_removal_plan
    from yt_downloader.safe_output import cleanup_private_staging_directory

    case_root = runner.run_root / "cases" / "lifecycle-staging-transitions"
    output_dir = case_root / "output"
    staging_root = output_dir / ".vfstage"
    staging_root.mkdir(parents=True, mode=0o700)
    (staging_root / ".DS_Store").write_bytes(b"synthetic Finder metadata")

    download_seen_at: list[float | None] = [None]

    def skip_when(events: Any, _app: Any) -> bool:
        observed = any(
            event.get("kind") == "status"
            and "downloading" in str(event.get("payload") or "").lower()
            for event in events.trace
        )
        if observed and download_seen_at[0] is None:
            download_seen_at[0] = time.monotonic()
        return bool(
            download_seen_at[0] is not None
            and time.monotonic() - download_seen_at[0] >= 0.2
        )

    skipped = runner.run_job(
        case_id="lifecycle-staging-skip",
        url=server.url("/slow/page"),
        output_type="MP4",
        output_dir=output_dir,
        cancel_when=skip_when,
        control_request="skip_video",
        cancel_timeout_seconds=20,
    )
    skipped_trace = skipped.get("staging_trace") or []
    skipped_active = any(
        snapshot.get("run_directories")
        and any(entry.get("kind") == "file" for entry in snapshot.get("entries") or [])
        for snapshot in skipped_trace
    )
    skipped_terminal_receipts = [
        event
        for event in skipped.get("events") or []
        if event.get("kind") == "item_terminal"
        and isinstance(event.get("payload"), dict)
        and isinstance(event["payload"].get("job"), dict)
        and event["payload"]["job"].get("terminal_status") == "Skipped"
        and event["payload"]["job"].get("terminal_message") == "Video skipped by user"
    ]
    skipped_terminal = len(skipped_terminal_receipts) == 1
    idle_after_skip = not staging_root.exists()

    completed = runner.run_job(
        case_id="lifecycle-staging-successor",
        url=server.url("/page/unicode?staging-lifecycle=successor"),
        output_type="MP4",
        output_dir=output_dir,
    )
    completed_trace = completed.get("staging_trace") or []
    successor_active = any(
        snapshot.get("run_directories")
        and any(entry.get("kind") == "file" for entry in snapshot.get("entries") or [])
        for snapshot in completed_trace
    )
    idle_after_completion = not staging_root.exists()

    library_stage = create_staging_dir(output_dir)
    (library_stage / "active-owner-sentinel").write_bytes(b"active transaction")
    terminal_info = {
        "id": "terminal-staging-fixture",
        "title": "Skipped staging lifecycle fixture",
        "vodforge_output_type": "MP4",
        "vodforge_terminal_run_id": "terminal-staging-run",
        "vodforge_terminal_status": "Skipped",
        "vodforge_terminal_message": "Video skipped by user",
    }
    library_app = make_headless_app(TracingQueue())
    library_app.download_history = []
    library_app.metadata_items = [terminal_info]
    library_app.pending_jobs = []
    library_app._terminal_jobs = []
    library_app._completed_jobs = []
    library_app._rebuild_output_dir_index = lambda: None
    removal_plan = resolve_library_removal_plan(
        terminal_info,
        active_job=None,
        pending_jobs=(),
    )
    library_app._apply_library_removal_plan(terminal_info, 0, removal_plan)
    active_stage_preserved_by_library_removal = (
        library_stage / "active-owner-sentinel"
    ).is_file()
    cleanup_private_staging_directory(library_stage)
    idle_after_owned_cleanup = not staging_root.exists()

    passed = bool(
        skipped_active
        and skipped_terminal
        and idle_after_skip
        and skipped.get("media_output_count") == 0
        and not skipped.get("staging_entries_after")
        and successor_active
        and completed.get("media_output_count") == 1
        and idle_after_completion
        and not completed.get("staging_entries_after")
        and active_stage_preserved_by_library_removal
        and idle_after_owned_cleanup
        and _worker_cleanup_is_clean(skipped)
        and _worker_cleanup_is_clean(completed)
    )
    scenario = {
        "id": "lifecycle.staging_transaction_transitions",
        "evidence_tier": "headless_production_pipeline",
        "category": "lifecycle",
        "status": "passed" if passed else "failed",
        "duration_seconds": round(
            float(skipped.get("duration_seconds") or 0)
            + float(completed.get("duration_seconds") or 0),
            4,
        ),
        "metrics": {
            "jobs_attempted": 2,
            "jobs_completed": int(completed.get("media_output_count") == 1),
            "jobs_failed": 0 if passed else 1,
            "jobs_cancelled": 0,
            "jobs_skipped": int(skipped_terminal),
            "skip_active_staging_observed": skipped_active,
            "skip_terminal_observed": skipped_terminal,
            "idle_root_absent_after_skip": idle_after_skip,
            "successor_active_staging_observed": successor_active,
            "idle_root_absent_after_completion": idle_after_completion,
            "active_stage_preserved_by_library_removal": (
                active_stage_preserved_by_library_removal
            ),
            "idle_root_absent_after_owned_cleanup": idle_after_owned_cleanup,
            "skip_staging_snapshot_count": len(skipped_trace),
            "successor_staging_snapshot_count": len(completed_trace),
        },
        "evidence": [
            f"Skip trace observed a private run directory with media files: {skipped_active}; snapshots={len(skipped_trace)}",
            f"Skip emitted exactly one truthful item terminal and left no idle root: {skipped_terminal and idle_after_skip}",
            f"Queued-successor equivalent created fresh staging and committed one output: {successor_active and completed.get('media_output_count') == 1}",
            f"Successful completion left no idle root: {idle_after_completion}",
            f"Library terminal-record removal preserved an independently active staging owner: {active_stage_preserved_by_library_removal}",
            f"The owning cleanup removed the final private root: {idle_after_owned_cleanup}",
        ],
        "artifacts": [
            str(case_root / "skip-staging-trace.json"),
            str(case_root / "successor-staging-trace.json"),
        ],
        "error": None,
    }
    (case_root / "skip-staging-trace.json").write_text(
        json.dumps(skipped_trace, indent=2) + "\n", encoding="utf-8"
    )
    (case_root / "successor-staging-trace.json").write_text(
        json.dumps(completed_trace, indent=2) + "\n", encoding="utf-8"
    )
    findings = (
        []
        if passed
        else [
            _finding_for_failed_scenario(
                scenario,
                "Private staging lifecycle diverged during skip, successor, completion, or Library removal",
                "reliability defect",
                "high",
                "same-volume staging lifecycle and Library ownership",
                "Keep each active transaction isolated, remove its private files and idle root at terminal return, and prevent Library history mutation from deleting independently active staging.",
            )
        ]
    )
    return scenario, findings


def lifecycle_soak(
    runner: HeadlessPipelineRunner,
    server: FixtureHTTPServer,
    *,
    jobs: int,
    detailed: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    recorder = LifecycleCheckpointRecorder(
        runner.run_root, jobs=jobs, detailed=detailed
    )
    stable_source_route = "/page/unicode?soak=controlled"
    stable_source_url = server.url(stable_source_route)
    baseline = recorder.start()
    compact_results: list[dict[str, Any]] = []
    rss_after_each_job: list[int] = []
    fds_after_each_job: list[int] = []
    threads_after_each_job: list[int] = []
    traced_python_after_each_job: list[int] = []
    started = time.monotonic()
    try:
        for index in range(jobs):
            job_index = index + 1
            recorder.before_job(job_index)
            result = runner.run_job(
                case_id=f"lifecycle-soak-{index + 1:03d}",
                url=stable_source_url,
                output_type="MP3",
                write_thumbnail=False,
                write_info_json=False,
                embed_cover_art=False,
                cleanup_global_children=False,
            )
            resources = result.get("resource_metrics") or {}
            children_before = [
                {
                    "pid": item.get("pid"),
                    "returncode": item.get("returncode"),
                    "alive": bool(item.get("alive")),
                }
                for item in result.get("active_children_before_harness_cleanup") or []
            ]
            output_dir = str((result.get("job") or {}).get("output_dir") or "")
            compact = {
                "case_id": str(result.get("case_id") or ""),
                "duration_seconds": result.get("duration_seconds"),
                "error": result.get("error"),
                "media_output_count": int(result.get("media_output_count") or 0),
                "staging_residue_count": len(result.get("staging_entries_after") or []),
                "peak_zombie_processes": int(
                    resources.get("peak_zombie_processes") or 0
                ),
                "peak_child_processes": int(resources.get("peak_child_processes") or 0),
                "active_children_before_harness_cleanup": children_before,
                "history_event_count": sum(
                    1
                    for event in result.get("events") or []
                    if event.get("kind") == "history_record"
                ),
                "artifact": str(Path(output_dir).parent / "pipeline-result.json"),
            }
            compact_results.append(compact)
            # The full result contains large duplicated event/metadata/probe trees.
            # Its artifact is already durable, so release it before post-GC sampling.
            del resources
            del children_before
            del result
            after = recorder.after_job(job_index, extra=compact)
            process_state = after.get("process") or {}
            rss = process_state.get("rss_bytes")
            if isinstance(rss, int):
                rss_after_each_job.append(rss)
            fds = process_state.get("fd_or_handle_count")
            if isinstance(fds, int):
                fds_after_each_job.append(fds)
            os_threads = process_state.get("os_thread_count")
            if isinstance(os_threads, int):
                threads_after_each_job.append(os_threads)
            traced_current = (after.get("tracemalloc") or {}).get("current_bytes")
            if isinstance(traced_current, int):
                traced_python_after_each_job.append(traced_current)
            del process_state
            del after
    finally:
        recorder.finish()

    baseline_process = baseline.get("process") or {}
    rss_before = baseline_process.get("rss_bytes")
    fds_before = baseline_process.get("fd_or_handle_count")
    rss_after = rss_after_each_job[-1] if rss_after_each_job else None
    fds_after = fds_after_each_job[-1] if fds_after_each_job else None
    rss_delta = (
        rss_after - rss_before
        if rss_before is not None and rss_after is not None
        else None
    )
    fd_delta = (
        fds_after - fds_before
        if fds_before is not None and fds_after is not None
        else None
    )
    failures = [
        result
        for result in compact_results
        if result.get("error") or result.get("media_output_count") != 1
    ]
    residues = sum(
        int(result.get("staging_residue_count") or 0) for result in compact_results
    )
    zombies = max(
        (int(result.get("peak_zombie_processes") or 0) for result in compact_results),
        default=0,
    )
    per_job_survivors = [
        {
            "case_id": result["case_id"],
            "children": [
                item
                for item in result.get("active_children_before_harness_cleanup") or []
                if item.get("alive")
            ],
        }
        for result in compact_results
        if any(
            item.get("alive")
            for item in result.get("active_children_before_harness_cleanup") or []
        )
    ]
    from yt_downloader import app as app_module

    survivors_before_cleanup = active_child_snapshot(app_module)
    if any(item["alive"] for item in survivors_before_cleanup):
        app_module.terminate_all_active_child_processes(
            deadline_monotonic=time.monotonic() + 3
        )
    survivors_after_cleanup = active_child_snapshot(app_module)
    monotonic_rss_growth = (
        len(rss_after_each_job) >= 3
        and all(left <= right for left, right in pairwise(rss_after_each_job))
        and rss_after_each_job[-1] > rss_after_each_job[0]
    )
    monotonic_fd_growth = (
        len(fds_after_each_job) >= 3
        and all(left <= right for left, right in pairwise(fds_after_each_job))
        and fds_after_each_job[-1] > fds_after_each_job[0]
    )
    rss_growth = lifecycle_growth_summary(rss_after_each_job)
    traced_growth = lifecycle_growth_summary(traced_python_after_each_job)
    final_sample: dict[str, Any] = {}
    final_storage: dict[str, Any] = {}
    if compact_results:
        try:
            final_sample = json.loads(
                recorder.samples_path.read_text(encoding="utf-8").splitlines()[-1]
            )
            final_storage = final_sample.get("storage") or {}
        except (IndexError, OSError, json.JSONDecodeError):
            final_sample = {}
            final_storage = {}

    (
        worker_counts_before,
        worker_counts_after,
        worker_count_deltas,
        retained_worker_object_deltas,
        retained_worker_growth_signal,
    ) = _worker_object_retention_receipt(baseline, final_sample)

    # Memory/FD trends are recorded for comparison. They do not become defects
    # from a machine-independent magic threshold in a single short run. Concrete
    # post-GC worker-object retention does fail this controlled lifecycle probe.
    passed = (
        not failures
        and residues == 0
        and zombies == 0
        and not per_job_survivors
        and not any(item["alive"] for item in survivors_before_cleanup)
        and not retained_worker_object_deltas
    )
    workload = {
        "contract": "controlled-repeated-worker-v2",
        "jobs": jobs,
        "source_route": stable_source_route,
        "fixture_item": "hls-short",
        "fixture_media": "generated 6-second 640x360 H.264/AAC",
        "output_type": "MP3",
        "mp3_bitrate_kbps": 192,
        "write_thumbnail": False,
        "write_info_json": False,
        "embed_cover_art": False,
        "tracemalloc_enabled": detailed,
        "full_pipeline_results_retained_during_sampling": False,
    }
    scenario = {
        "id": "lifecycle.repeated_job_soak",
        "evidence_tier": "headless_production_pipeline",
        "category": "lifecycle",
        "status": "passed" if passed else "failed",
        "duration_seconds": round(time.monotonic() - started, 4),
        "workload": workload,
        "metrics": {
            "jobs_attempted": jobs,
            "jobs_completed": jobs - len(failures),
            "jobs_failed": len(failures),
            "rss_before_bytes": rss_before,
            "rss_after_bytes": rss_after,
            "rss_delta_bytes": rss_delta,
            "fd_before": fds_before,
            "fd_after": fds_after,
            "fd_delta": fd_delta,
            "staging_residue_count": residues,
            "peak_zombie_processes": zombies,
            "orphaned_child_processes": sum(
                1 for item in survivors_before_cleanup if item.get("alive")
            ),
            "job_durations_seconds": [
                result.get("duration_seconds") for result in compact_results
            ],
            "rss_after_each_job_bytes": rss_after_each_job,
            "fds_after_each_job": fds_after_each_job,
            "os_threads_after_each_job": threads_after_each_job,
            "traced_python_after_each_job_bytes": traced_python_after_each_job,
            "rss_growth_description": rss_growth,
            "traced_python_growth_description": traced_growth,
            "monotonic_rss_growth_signal": monotonic_rss_growth,
            "monotonic_fd_growth_signal": monotonic_fd_growth,
            "worker_object_counts_before": worker_counts_before,
            "worker_object_counts_after": worker_counts_after,
            "worker_object_count_deltas": worker_count_deltas,
            "retained_worker_object_deltas": retained_worker_object_deltas,
            "retained_worker_object_growth_signal": retained_worker_growth_signal,
            "single_run_growth_conclusion": "comparison_required",
            "per_job_active_child_survivors": per_job_survivors,
            "active_children_before_emergency_cleanup": survivors_before_cleanup,
            "active_children_after_emergency_cleanup": survivors_after_cleanup,
            "thumbnail_cache": final_storage.get("thumbnail_cache"),
            "history_file": final_storage.get("history_file"),
            "headless_tk_image_count": None,
            "headless_tk_visibility": "unavailable_headless_no_tk_initialization",
            "headless_in_memory_history_count": None,
            "headless_history_visibility": "unavailable_ui_event_queue_not_pumped",
            "observation_artifact": str(recorder.samples_path),
        },
        "evidence": [
            f"Repeated real jobs: {jobs}; failures: {len(failures)}",
            f"RSS delta after GC: {rss_delta} bytes (machine/run signal, not universal threshold)",
            f"File descriptor delta: {fd_delta}",
            f"Staging residue: {residues}; peak zombies: {zombies}",
            f"Post-warmup RSS description: {rss_growth}",
            f"Post-GC retained worker object deltas: {retained_worker_object_deltas}",
            f"Per-job child survivors: {per_job_survivors}; final survivors: {survivors_before_cleanup}",
            "Tk images and in-memory UI history are unavailable in this headless worker tier, not observed as zero.",
            "RSS and allocation trends remain comparison-required evidence; this scenario has no universal leak threshold.",
        ],
        "artifacts": [str(result["artifact"]) for result in compact_results]
        + recorder.artifacts,
        "error": None,
    }
    findings = (
        []
        if passed
        else [
            _finding_for_failed_scenario(
                scenario,
                "Repeated real jobs show failures, lifecycle residue, or retained worker objects",
                "reliability defect",
                "medium",
                "worker/object/process/temp lifecycle",
                "Use the post-GC object and per-job ownership receipts to repair the first retained worker object, failed output, unreaped child, zombie, or staging owner without converting RSS alone into a defect.",
            )
        ]
    )
    return scenario, findings


def concurrency_mixed(
    runner: HeadlessPipelineRunner, server: FixtureHTTPServer
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    results: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    lock = threading.Lock()

    def execute(name: str, output_type: str) -> None:
        try:
            result = runner.run_job(
                case_id=f"concurrency-{name}",
                url=server.url(f"/page/unicode?concurrent={name}"),
                output_type=output_type,
                write_thumbnail=False,
                write_info_json=False,
                embed_cover_art=False,
                cleanup_global_children=False,
            )
            with lock:
                results[name] = result
        except Exception as exc:  # noqa: BLE001 - preserve each attacked worker's terminal evidence
            with lock:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")

    started = time.monotonic()
    threads = [
        threading.Thread(
            target=execute, args=("mp4", "MP4"), name="quality-concurrency-mp4"
        ),
        threading.Thread(
            target=execute, args=("mp3", "MP3"), name="quality-concurrency-mp3"
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    from yt_downloader import app as app_module

    survivors_before_cleanup = active_child_snapshot(app_module)
    if any(item["alive"] for item in survivors_before_cleanup):
        app_module.terminate_all_active_child_processes(
            deadline_monotonic=time.monotonic() + 3
        )
    survivors_after_cleanup = active_child_snapshot(app_module)
    alive = [thread.name for thread in threads if thread.is_alive()]
    failures = [
        name
        for name, result in results.items()
        if result.get("error") or result.get("media_output_count") != 1
    ]
    residues = {
        name: result.get("staging_entries_after")
        for name, result in results.items()
        if result.get("staging_entries_after")
    }
    passed = (
        len(results) == 2
        and not errors
        and not alive
        and not failures
        and not residues
        and not any(item["alive"] for item in survivors_before_cleanup)
    )
    scenario = {
        "id": "concurrency.simultaneous_worker_attack",
        "evidence_tier": "headless_production_pipeline",
        "category": "concurrency",
        "status": "passed" if passed else "failed",
        "duration_seconds": round(time.monotonic() - started, 4),
        "metrics": {
            "workers_started": 2,
            "workers_completed": len(results),
            "jobs_attempted": 2,
            "jobs_completed": sum(
                1
                for result in results.values()
                if not result.get("error") and result.get("media_output_count") == 1
            ),
            "jobs_failed": len(failures) + len(errors),
            "jobs_cancelled": 0,
            "alive_after_timeout": alive,
            "failed_workers": failures,
            "staging_residue": residues,
            "active_children_before_emergency_cleanup": survivors_before_cleanup,
            "orphaned_child_processes": sum(
                1 for item in survivors_before_cleanup if item.get("alive")
            ),
            "active_children_after_emergency_cleanup": survivors_after_cleanup,
        },
        "evidence": [
            "This is an adversarial unsupported simultaneous-worker attack; the product UI intentionally serializes its queue.",
            f"Completed workers: {sorted(results)}; failures: {failures}; still alive: {alive}",
            f"Per-worker media outputs: { {name: result.get('media_output_count') for name, result in results.items()} }",
            f"Staging residue: {residues}",
            f"Production child-registry survivors before harness emergency cleanup: {survivors_before_cleanup}",
        ],
        "artifacts": [
            str(Path(result["job"]["output_dir"]).parent / "pipeline-result.json")
            for result in results.values()
        ],
        "error": "; ".join(errors) if errors else None,
    }
    findings = (
        []
        if passed
        else [
            _finding_for_failed_scenario(
                scenario,
                "Adversarial simultaneous workers produced inconsistent or incomplete state",
                "reliability defect",
                "medium",
                "global child tracking, diagnostics, and worker state",
                "Keep the supported UI queue serialized and capability-gate worker construction; make global lifecycle registries safe under defensive concurrent invocation.",
            )
        ]
    )
    return scenario, findings


def public_w3c_probe(
    runner: HeadlessPipelineRunner,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    url = "https://media.w3.org/2010/05/sintel/trailer.mp4"
    result = runner.run_job(
        case_id="public-w3c-sintel", url=url, output_type="MP4", quality_label="480p"
    )
    # Generic direct URLs are a discovered boundary, not a user-facing YouTube promise.
    clean = (
        (result.get("error") is None and result.get("media_output_count") == 1)
        or (bool(result.get("error")) and result.get("media_output_count") == 0)
    ) and not result.get("staging_entries_after")
    scenario = _scenario_from_pipeline(
        scenario_id="correctness.public_w3c_generic_boundary",
        category="correctness",
        result=result,
        passed=clean,
        evidence=[
            "W3C explicitly published this Sintel trailer for HTML media testing; the underlying film is CC BY 3.0.",
            f"Generic-source outcome: {'validated output' if result.get('media_output_count') else 'explicit rejection'}; error={result.get('error')}",
            f"Committed media outputs: {result.get('media_output_count')}; staging residue: {result.get('staging_entries_after')}",
            "This scenario does not treat generic URL support as promised VODForge behavior; it tests boundary cleanliness.",
        ],
        metrics={"external_public_media": True},
    )
    return scenario, [] if clean else [
        _finding_for_failed_scenario(
            scenario,
            "Public generic-media boundary produced corruption or residue",
            "reliability defect",
            "medium",
            "generic yt-dlp extractor boundary",
            "Either reject unsupported providers before work or preserve the existing real pipeline's clean failure/commit guarantees.",
        )
    ]


def packaged_e2e_placeholder(
    e2e_result: Path | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if e2e_result is None or not e2e_result.is_file():
        return {
            "id": "packaged_app_e2e.full_journey",
            "evidence_tier": "packaged_app_e2e",
            "category": "full application E2E",
            "status": "skipped",
            "duration_seconds": 0.0,
            "metrics": {
                "artifact_observed": False,
                "ui_interaction_observed": False,
                "final_output_probed": False,
            },
            "evidence": [
                "No packaged-app E2E receipt was supplied to this run.",
                "Headless pipeline successes are intentionally not counted as complete-application evidence.",
                "Run ./engineering-quality/run packaged-e2e to produce an artifact/UI/worker/output journey receipt.",
            ],
            "artifacts": [],
            "error": None,
        }, []
    payload = json.loads(e2e_result.read_text(encoding="utf-8"))
    scenario = payload.get("scenario")
    problems: list[str] = []
    if payload.get("schema_version") != "1.0.0":
        problems.append(
            f"unexpected E2E schema_version={payload.get('schema_version')!r}"
        )
    if not isinstance(scenario, dict):
        problems.append("receipt has no scenario object")
        scenario = {}
    if scenario.get("id") != "packaged_app_e2e.full_journey":
        problems.append(f"unexpected scenario id={scenario.get('id')!r}")
    if scenario.get("evidence_tier") != "packaged_app_e2e":
        problems.append(f"unexpected evidence tier={scenario.get('evidence_tier')!r}")
    if scenario.get("status") not in {"passed", "failed", "error", "skipped"}:
        problems.append(f"invalid scenario status={scenario.get('status')!r}")
    artifact_receipt = payload.get("artifact_receipt")
    if not isinstance(artifact_receipt, dict) or not artifact_receipt.get(
        "executable_sha256"
    ):
        problems.append("receipt has no packaged executable identity")
    elif (
        artifact_receipt.get("policy_verified") is not True
        or not isinstance(artifact_receipt.get("bundle_tree"), dict)
        or not artifact_receipt["bundle_tree"].get("sha256")
    ):
        problems.append("receipt has no verified artifact policy and bundle identity")
    candidate_binding = payload.get("candidate_binding")
    if (
        not isinstance(candidate_binding, dict)
        or candidate_binding.get("verified") is not True
        or not candidate_binding.get("candidate_id")
        or not candidate_binding.get("archive_sha256")
        or not candidate_binding.get("bundle_tree_sha256")
    ):
        problems.append("receipt is not bound to one verified immutable candidate")
    artifact_integrity = payload.get("artifact_integrity")
    if (
        not isinstance(artifact_integrity, dict)
        or artifact_integrity.get("verified") is not True
    ):
        problems.append("receipt has no verified post-E2E artifact integrity")
    process_provenance = payload.get("process_provenance")
    if (
        not isinstance(process_provenance, dict)
        or process_provenance.get("verified") is not True
    ):
        problems.append("receipt has no verified isolated process provenance")
    trace_validation = payload.get("driver_trace_validation")
    if (
        not isinstance(trace_validation, dict)
        or trace_validation.get("provenance_required") is not True
        or trace_validation.get("invalid_provenance_events")
    ):
        problems.append("receipt driver events are not bound to attested launches")
    if not isinstance(payload.get("driver_trace"), dict) or not isinstance(
        payload.get("launches"), list
    ):
        problems.append("receipt has no structured driver trace and launch list")
    if not payload.get("started_at") or not payload.get("completed_at"):
        problems.append("receipt has no start/completion timestamps")
    if problems:
        invalid = {
            "id": "packaged_app_e2e.full_journey",
            "evidence_tier": "packaged_app_e2e",
            "category": "full application E2E",
            "status": "error",
            "duration_seconds": 0.0,
            "metrics": {"receipt_valid": False, "receipt_validation_errors": problems},
            "evidence": [
                f"Rejected packaged-app E2E receipt: {problem}" for problem in problems
            ],
            "artifacts": [str(e2e_result)],
            "error": "invalid packaged-app E2E receipt",
        }
        return invalid, [
            _finding_for_failed_scenario(
                invalid,
                "Packaged-app E2E receipt failed tier and provenance validation",
                "maintainability risk",
                "medium",
                "engineering-quality packaged E2E result import",
                "Regenerate the E2E receipt with this checkout's versioned driver protocol; never coerce a missing or wrong tier into packaged-app evidence.",
            )
        ]
    imported = dict(scenario)
    imported["artifacts"] = [*list(imported.get("artifacts") or []), str(e2e_result)]
    imported.setdefault("metrics", {})["receipt_valid"] = True
    return imported, list(payload.get("findings") or [])


def _expected_evidence_tier(scenario_id: str) -> str:
    if scenario_id.startswith("packaged_app_e2e."):
        return "packaged_app_e2e"
    if scenario_id.startswith(
        ("unit_static.", "maintainability.", "security.", "correctness.fresh_output_")
    ):
        return "unit_static"
    return "headless_production_pipeline"


def run_scenarios(
    *,
    repo_root: Path,
    harness_root: Path,
    run_root: Path,
    server: FixtureHTTPServer,
    profile: str,
    soak_jobs: int | None,
    include_public: bool,
    selected: set[str] | None,
    e2e_result: Path | None,
    progress: Callable[[str], None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runner = HeadlessPipelineRunner(run_root)
    deep = profile == "deep"
    lifecycle_jobs = (
        soak_jobs if deep and soak_jobs is not None else (50 if deep else 3)
    )
    registry: list[
        tuple[str, Callable[[], tuple[dict[str, Any], list[dict[str, Any]]]]]
    ] = [
        (
            "correctness.local_mp4_real_pipeline",
            lambda: correctness_mp4(runner, server),
        ),
        (
            "correctness.local_mp3_bitrate_real_pipeline",
            lambda: correctness_mp3(runner, server),
        ),
        (
            "correctness.local_mp4_embedding_disabled",
            lambda: correctness_mp4_embedding_disabled(runner, server),
        ),
        (
            "correctness.source_quality_selection_360p",
            lambda: correctness_source_quality(
                runner,
                server,
                requested_label="360p",
                expected_source_height=360,
            ),
        ),
        (
            "correctness.source_quality_selection_720p",
            lambda: correctness_source_quality(
                runner,
                server,
                requested_label="720p",
                expected_source_height=540,
            ),
        ),
        (
            "correctness.fresh_output_plan_validation",
            lambda: fresh_output_contract_probe(
                run_root / "cases" / "fresh-output-contract"
            ),
        ),
        (
            "reliability.http_404_cleanup",
            lambda: reliability_http_failure(runner, server),
        ),
        ("reliability.transient_http_retry", lambda: reliability_retry(runner, server)),
        (
            "reliability.cancel_during_slow_download",
            lambda: reliability_cancel(runner, server),
        ),
        (
            "reliability.cancel_during_transcode",
            lambda: reliability_cancel_transcode(runner, server),
        ),
        (
            "reliability.network_interruption_recovery",
            lambda: reliability_interrupted_transfer(runner, server),
        ),
        (
            "reliability.unwritable_output_directory",
            lambda: reliability_unwritable_output(runner),
        ),
        (
            "reliability.ffmpeg_child_failure",
            lambda: reliability_ffmpeg_failure(runner, server),
        ),
        (
            "reliability.batch_failure_report_reset",
            lambda: batch_failure_report_reset_probe(
                run_root / "cases" / "reliability-batch-report-reset"
            ),
        ),
        (
            "unit_static.activity_log_failure_receipt",
            lambda: activity_log_failure_receipt_probe(
                run_root / "cases" / "activity-log-failure-receipt"
            ),
        ),
        ("reliability.malformed_url", lambda: reliability_malformed(runner)),
        (
            "lifecycle.repeated_job_soak",
            lambda: lifecycle_soak(
                runner,
                server,
                jobs=lifecycle_jobs,
                detailed=deep,
            ),
        ),
        (
            "lifecycle.staging_transaction_transitions",
            lambda: lifecycle_staging_transitions(runner, server),
        ),
        (
            "lifecycle.quit_restart_recovery",
            lambda: lifecycle_quit_restart_recovery(runner),
        ),
        (
            "concurrency.simultaneous_worker_attack",
            lambda: concurrency_mixed(runner, server),
        ),
        (
            "security.path_and_subprocess_arguments",
            lambda: path_and_subprocess_probe(
                run_root / "cases" / "security-path-command", repo_root
            ),
        ),
        (
            "security.symlink_containment_and_staging_permissions",
            lambda: symlink_and_temp_probe(run_root / "cases" / "security-symlink"),
        ),
        (
            "security.url_secret_persistence",
            lambda: url_secret_persistence_probe(
                run_root / "cases" / "security-url-secret"
            ),
        ),
        (
            "security.thumbnail_network_authority",
            lambda: thumbnail_network_authority_probe(
                run_root / "cases" / "security-thumbnail-network",
                server,
            ),
        ),
        (
            "maintainability.change_surface",
            lambda: change_surface_probe(repo_root, harness_root),
        ),
        (
            "unit_static.repository_suite",
            lambda: run_static_suite(
                repo_root, run_root / "cases" / "static", deep=deep
            ),
        ),
        (
            "unit_static.bounded_mutation_history",
            lambda: run_bounded_mutation_campaign(
                repo_root, run_root / "cases" / "mutation-history"
            ),
        ),
        ("packaged_app_e2e.full_journey", lambda: packaged_e2e_placeholder(e2e_result)),
    ]
    if include_public or deep:
        registry.insert(
            2,
            (
                "correctness.public_w3c_generic_boundary",
                lambda: public_w3c_probe(runner),
            ),
        )
    scenarios: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for scenario_id, execute in registry:
        if selected and scenario_id not in selected:
            continue
        progress(scenario_id)
        started = time.monotonic()
        try:
            scenario, scenario_findings = execute()
            if not scenario.get("duration_seconds"):
                scenario["duration_seconds"] = round(time.monotonic() - started, 4)
        except Exception as exc:  # noqa: BLE001 - convert a scenario crash into a reportable harness error
            scenario = {
                "id": scenario_id,
                "evidence_tier": _expected_evidence_tier(scenario_id),
                "category": scenario_id.split(".", 1)[0],
                "status": "error",
                "duration_seconds": round(time.monotonic() - started, 4),
                "metrics": {},
                "evidence": [f"Harness scenario raised {type(exc).__name__}: {exc}"],
                "artifacts": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
            scenario_findings = [
                _finding_for_failed_scenario(
                    scenario,
                    "Harness scenario could not produce a valid result",
                    "code smell",
                    "medium",
                    "engineering-quality harness or production seam",
                    "Reproduce the recorded exception, determine whether the harness contract or production seam changed, and add a harness self-test.",
                )
            ]
        scenarios.append(scenario)
        findings.extend(scenario_findings)
    return scenarios, findings
