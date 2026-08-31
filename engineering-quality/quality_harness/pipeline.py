from __future__ import annotations

import dataclasses
import json
import queue
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .metrics import ResourceSampler
from .util import sha256_file, tree_size


class TracingQueue(queue.Queue[tuple[str, Any]]):
    def __init__(self) -> None:
        super().__init__()
        self.started = time.monotonic()
        self.trace: list[dict[str, Any]] = []
        self._trace_lock = threading.Lock()

    def put(
        self, item: tuple[str, Any], block: bool = True, timeout: float | None = None
    ) -> None:
        kind, payload = item
        with self._trace_lock:
            self.trace.append(
                {
                    "elapsed_seconds": round(time.monotonic() - self.started, 4),
                    "kind": str(kind),
                    "payload": _jsonable(payload),
                }
            )
        super().put(item, block=block, timeout=timeout)


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if field.repr
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def configure_production_sandbox(run_root: Path) -> dict[str, str]:
    """Redirect production-local diagnostic state into this harness run."""
    import yt_downloader.app as app_module

    diagnostics = run_root / "production-state" / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    app_module.DIAGNOSTICS_LOG_PATH = diagnostics / "latest.log"
    app_module.ACTIVITY_LOG_PATH = diagnostics / "activity.log"
    app_module.BATCH_FAILURE_REPORT_PATH = diagnostics / "batch-url-failures.txt"
    app_module.reset_diagnostics_log()
    app_module.prepare_activity_log(app_module.ACTIVITY_LOG_PATH)
    return {
        "diagnostics": str(app_module.DIAGNOSTICS_LOG_PATH),
        "activity": str(app_module.ACTIVITY_LOG_PATH),
        "batch_failures": str(app_module.BATCH_FAILURE_REPORT_PATH),
    }


def make_headless_app(events: TracingQueue) -> Any:
    """Construct only the state required by the real production worker seam."""
    from yt_downloader.app import DownloaderApp, ProviderNetworkCoordinator

    app = DownloaderApp.__new__(DownloaderApp)
    app.events = events
    app.cancel_requested = False
    app.skip_video_requested = False
    app.skip_url_requested = False
    app._active_progress_context = None
    app._last_progress_event_at = 0.0
    app.video_output_dirs_by_id = {}
    app._provider_network = ProviderNetworkCoordinator()
    return app


def build_job(
    *,
    url: str,
    output_dir: Path,
    output_type: str,
    quality_label: str = "360p",
    mp3_bitrate_kbps: int = 192,
    write_thumbnail: bool = True,
    write_info_json: bool = True,
    embed_metadata: bool = True,
    embed_cover_art: bool = True,
    embed_thumbnail: bool = False,
    single_video_only: bool = True,
    tags: list[str] | None = None,
) -> Any:
    from yt_downloader.app import (
        DownloadJob,
        ExportMode,
        ManualExportSettings,
        Mp3ExportSettings,
        OutputType,
    )

    selected_type = OutputType(output_type.upper())
    return DownloadJob(
        url=url,
        urls=[url],
        output_dir=output_dir,
        output_type=selected_type,
        quality_label=quality_label,
        export_mode=ExportMode.AUTO_CBR,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(
            bitrate_kbps=mp3_bitrate_kbps,
            embed_metadata=embed_metadata,
            embed_cover_art=embed_cover_art,
        ),
        single_video_only=single_video_only,
        use_nvenc=False,
        embed_thumbnail=embed_thumbnail if selected_type == OutputType.MP4 else False,
        write_thumbnail=write_thumbnail,
        embed_metadata=embed_metadata,
        write_info_json=write_info_json,
        tags=list(tags or ["vodforge-quality", "synthetic-fixture", "unicode-Δ"]),
    )


def _diagnostic_timing(text: str) -> dict[str, Any]:
    patterns = {
        "playlist_detection_seconds": r"playlist detection elapsed_seconds=([0-9.]+)",
        "source_analysis_seconds": r"analysis completed elapsed_seconds=([0-9.]+)",
        "download_and_postprocess_seconds": r"download and yt-dlp post-processing elapsed_seconds=([0-9.]+)",
        "transcode_seconds": r"transcode elapsed_seconds=([0-9.]+)",
        "validation_seconds": r"artifact validation elapsed_seconds=([0-9.]+)",
        "atomic_commit_seconds": r"atomic output commit elapsed_seconds=([0-9.]+)",
    }
    timings: dict[str, Any] = {}
    for name, pattern in patterns.items():
        values = [float(match) for match in re.findall(pattern, text)]
        if values:
            timings[name] = round(sum(values), 4)
            timings[f"{name}_samples"] = [round(value, 4) for value in values]
    return timings


def _output_files(output_dir: Path) -> list[Path]:
    if not output_dir.exists():
        return []
    return sorted(
        (
            path
            for path in output_dir.rglob("*")
            if path.is_file() and ".vfstage" not in path.parts and not path.is_symlink()
        ),
        key=lambda item: str(item),
    )


def _probe_outputs(paths: list[Path], ffprobe: str | None) -> list[dict[str, Any]]:
    from yt_downloader.app import run_ffprobe_json

    probed: list[dict[str, Any]] = []
    for path in paths:
        entry: dict[str, Any] = {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        if path.suffix.lower() in {".mp4", ".mp3", ".m4a", ".webm", ".mov"} and ffprobe:
            try:
                entry["ffprobe"] = run_ffprobe_json(ffprobe, path)
                entry["readable"] = True
            except Exception as exc:  # noqa: BLE001 - record any independent probe failure as evidence
                entry["readable"] = False
                entry["probe_error"] = f"{type(exc).__name__}: {exc}"
        probed.append(entry)
    return probed


def _latest_metadata(trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(trace):
        if event.get("kind") != "job_metadata":
            continue
        payload = event.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("info"), dict):
            return payload["info"]
    return None


def active_child_snapshot(app_module: Any) -> list[dict[str, Any]]:
    """Read the production child registry without mutating lifecycle state."""
    with app_module._ACTIVE_CHILD_PROCESS_LOCK:
        active = tuple(app_module._ACTIVE_CHILD_PROCESSES)
    snapshot: list[dict[str, Any]] = []
    for process in active:
        poll = getattr(process, "poll", None)
        returncode = poll() if callable(poll) else None
        snapshot.append(
            {
                "pid": getattr(process, "pid", None),
                "returncode": returncode,
                "alive": returncode is None,
            }
        )
    return snapshot


class StagingTraceRecorder:
    """Observe private staging topology without reading media contents."""

    def __init__(self, output_dir: Path, events: TracingQueue) -> None:
        self.output_dir = output_dir
        self.events = events
        self.trace: list[dict[str, Any]] = []
        self._last_signature: tuple[object, ...] | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._monitor,
            name="quality-staging-trace",
            daemon=True,
        )

    def _status(self) -> str:
        for event in reversed(self.events.trace):
            if event.get("kind") == "status":
                return str(event.get("payload") or "")
        return ""

    def _snapshot(self, *, final: bool = False) -> None:
        staging_root = self.output_dir / ".vfstage"
        entries: list[dict[str, Any]] = []
        root_present = False
        try:
            root_stat = staging_root.lstat()
            root_present = not staging_root.is_symlink() and staging_root.is_dir()
            root_mode = root_stat.st_mode & 0o777
        except (FileNotFoundError, OSError):
            root_mode = None
        if root_present:
            try:
                candidates = sorted(staging_root.rglob("*"), key=lambda path: str(path))
            except OSError:
                candidates = []
            for path in candidates:
                try:
                    path_stat = path.lstat()
                    relative = str(path.relative_to(staging_root))
                    if path.is_symlink():
                        kind = "symlink"
                    elif path.is_dir():
                        kind = "directory"
                    elif path.is_file():
                        kind = "file"
                    else:
                        kind = "other"
                    entries.append(
                        {
                            "path": relative,
                            "kind": kind,
                            "size_bytes": path_stat.st_size if kind == "file" else None,
                        }
                    )
                except (FileNotFoundError, OSError, ValueError):
                    continue
        status = self._status()
        signature = (
            root_present,
            root_mode,
            status,
            tuple((entry["path"], entry["kind"]) for entry in entries),
        )
        if not final and signature == self._last_signature:
            return
        self._last_signature = signature
        self.trace.append(
            {
                "elapsed_seconds": round(time.monotonic() - self.events.started, 4),
                "status": status,
                "root_present": root_present,
                "root_mode": root_mode,
                "run_directories": [
                    entry["path"]
                    for entry in entries
                    if entry["kind"] == "directory" and "/" not in entry["path"]
                ],
                "entries": entries,
                "final": final,
            }
        )

    def _monitor(self) -> None:
        self._snapshot()
        while not self._stop.wait(0.02):
            self._snapshot()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> list[dict[str, Any]]:
        self._stop.set()
        self._thread.join(timeout=2)
        self._snapshot(final=True)
        return self.trace


class HeadlessPipelineRunner:
    """High-volume adapter over VODForge's real production download worker."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = run_root

    def run_job(
        self,
        *,
        case_id: str,
        url: str,
        output_type: str,
        quality_label: str = "360p",
        mp3_bitrate_kbps: int = 192,
        write_thumbnail: bool = True,
        write_info_json: bool = True,
        embed_metadata: bool = True,
        embed_cover_art: bool = True,
        embed_thumbnail: bool = False,
        output_dir: Path | None = None,
        cancel_when: Callable[[TracingQueue, Any], bool] | None = None,
        control_request: str = "cancel",
        cancel_timeout_seconds: float = 15,
        validate_destination: bool = True,
        re_raise: bool = True,
        cleanup_global_children: bool = True,
        ffmpeg_override: str | None = None,
    ) -> dict[str, Any]:
        import yt_downloader.app as app_module

        case_dir = self.run_root / "cases" / case_id
        output_dir = output_dir or case_dir / "output"
        case_dir.mkdir(parents=True, exist_ok=True)
        events = TracingQueue()
        app = make_headless_app(events)
        if ffmpeg_override is not None:
            app._find_ffmpeg = lambda: ffmpeg_override
        progress_trace: list[dict[str, Any]] = []
        production_progress_hook = app._progress_hook

        def traced_progress(data: dict[str, Any]) -> None:
            progress_trace.append(
                {
                    "elapsed_seconds": round(time.monotonic() - events.started, 4),
                    "status": data.get("status"),
                    "downloaded_bytes": data.get("downloaded_bytes"),
                    "total_bytes": data.get("total_bytes")
                    or data.get("total_bytes_estimate"),
                    "speed_bytes_per_second": data.get("speed"),
                    "eta_seconds": data.get("eta"),
                    "filename": str(data.get("filename") or ""),
                }
            )
            production_progress_hook(data)

        app._progress_hook = traced_progress
        job = build_job(
            url=url,
            output_dir=output_dir,
            output_type=output_type,
            quality_label=quality_label,
            mp3_bitrate_kbps=mp3_bitrate_kbps,
            write_thumbnail=write_thumbnail,
            write_info_json=write_info_json,
            embed_metadata=embed_metadata,
            embed_cover_art=embed_cover_art,
            embed_thumbnail=embed_thumbnail,
        )
        diagnostic_path = Path(app_module.DIAGNOSTICS_LOG_PATH)
        marker = f"QUALITY CASE {case_id} {job.run_id}"
        app_module.write_diagnostic(f"{marker} START")
        diagnostic_start = (
            diagnostic_path.stat().st_size if diagnostic_path.exists() else 0
        )
        sampler = ResourceSampler(case_dir).start()
        started = time.monotonic()
        outcome: Any = None
        error: str | None = None
        cancellation_thread: threading.Thread | None = None
        staging_recorder = StagingTraceRecorder(output_dir, events)
        staging_recorder.start()

        if cancel_when is not None:

            def cancellation_watch() -> None:
                deadline = time.monotonic() + cancel_timeout_seconds
                while time.monotonic() < deadline:
                    if cancel_when(events, app):
                        if control_request == "skip_video":
                            app.skip_video_requested = True
                        else:
                            app.cancel_requested = True
                        app_module.terminate_all_active_child_processes()
                        return
                    time.sleep(0.02)

            cancellation_thread = threading.Thread(
                target=cancellation_watch, name=f"quality-cancel-{case_id}", daemon=True
            )
            cancellation_thread.start()
        try:
            if validate_destination:
                app_module.validate_output_directory_access(output_dir)
            outcome = app._download_worker_single(job, re_raise=re_raise)
        except Exception as exc:  # noqa: BLE001 - production failures are the subject of the harness
            error = f"{type(exc).__name__}: {exc}"
        finally:
            duration = time.monotonic() - started
            if cancellation_thread is not None:
                cancellation_thread.join(timeout=1)
            staging_trace = staging_recorder.stop()
            resource_metrics = sampler.stop()
            active_children_before_harness_cleanup = active_child_snapshot(app_module)
            if cleanup_global_children and any(
                item["alive"] for item in active_children_before_harness_cleanup
            ):
                # This is emergency containment after the observation, not product
                # evidence. Recording first prevents the harness from hiding leaks.
                app_module.terminate_all_active_child_processes(
                    deadline_monotonic=time.monotonic() + 3
                )
            active_children_after_harness_cleanup = active_child_snapshot(app_module)
            app_module.write_diagnostic(f"{marker} END")

        diagnostics = ""
        if diagnostic_path.exists():
            with diagnostic_path.open("rb") as handle:
                handle.seek(min(diagnostic_start, diagnostic_path.stat().st_size))
                diagnostics = handle.read().decode("utf-8", errors="replace")
        files = _output_files(output_dir)
        ffprobe = app._find_ffprobe() or app_module._ffprobe_for_ffmpeg(
            app._find_ffmpeg() or ""
        )
        output_probes = _probe_outputs(files, ffprobe)
        media_outputs = [
            entry
            for entry in output_probes
            if Path(entry["path"]).suffix.lower() in {".mp4", ".mp3"}
        ]
        first_download_event = next(
            (
                float(event["elapsed_seconds"])
                for event in events.trace
                if event.get("kind") == "status"
                and "— downloading" in str(event.get("payload") or "")
            ),
            None,
        )
        downloaded_bytes = max(
            (int(point.get("downloaded_bytes") or 0) for point in progress_trace),
            default=0,
        )
        download_seconds = _diagnostic_timing(diagnostics).get(
            "download_and_postprocess_seconds"
        )
        throughput = (
            downloaded_bytes / float(download_seconds)
            if downloaded_bytes
            and isinstance(download_seconds, (int, float))
            and download_seconds > 0
            else None
        )
        stage_entries = (
            [str(path) for path in output_dir.rglob("*") if ".vfstage" in path.parts]
            if output_dir.exists()
            else []
        )
        result = {
            "case_id": case_id,
            "pipeline_entrypoint": "yt_downloader.app.DownloaderApp._download_worker_single",
            "job": {
                "run_id": job.run_id,
                "url": url,
                "output_type": output_type.upper(),
                "quality_label": quality_label,
                "embed_thumbnail": job.embed_thumbnail,
                "embed_metadata": job.embed_metadata,
                "requested_mp3_bitrate_kbps": mp3_bitrate_kbps
                if output_type.upper() == "MP3"
                else None,
                "output_dir": str(output_dir),
            },
            "duration_seconds": round(duration, 4),
            "job_initialization_seconds": first_download_event,
            "outcome": _jsonable(outcome),
            "error": error,
            "cancel_requested": bool(app.cancel_requested),
            "skip_video_requested": bool(app.skip_video_requested),
            "control_request": control_request if cancel_when is not None else None,
            "events": events.trace,
            "progress_trace": progress_trace,
            "latest_metadata": _latest_metadata(events.trace),
            "outputs": output_probes,
            "media_output_count": len(media_outputs),
            "output_bytes": tree_size(output_dir),
            "staging_entries_after": stage_entries,
            "staging_trace": staging_trace,
            "diagnostic_timings": _diagnostic_timing(diagnostics),
            "effective_throughput_bytes_per_second": round(throughput, 3)
            if throughput
            else None,
            "resource_metrics": resource_metrics,
            "active_children_before_harness_cleanup": active_children_before_harness_cleanup,
            "active_children_after_harness_cleanup": active_children_after_harness_cleanup,
            "harness_emergency_cleanup_used": bool(
                cleanup_global_children
                and any(
                    item["alive"] for item in active_children_before_harness_cleanup
                )
            ),
            "diagnostics_path": str(diagnostic_path),
            "diagnostic_excerpt": diagnostics[-12000:],
        }
        (case_dir / "pipeline-result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result
