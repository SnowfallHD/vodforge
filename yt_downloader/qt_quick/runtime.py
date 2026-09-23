"""Qt-neutral adapter for the existing serialized download and history owners.

The worker remains the production worker. This adapter owns only thread/event
handoff and refuses new work when durable run or history recovery is blocked.
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from yt_downloader.app import (
    DownloadWorkerCore,
    ProviderNetworkCoordinator,
    set_active_child_process_observer,
    single_video_url_requires_video_id_error,
    validate_output_directory_access,
)
from yt_downloader.history import (
    RETRY_JOB_METADATA_KEY,
    HistoryError,
    file_operations_pending,
    history_file_path,
    load_history,
    sanitize_run_activity,
    save_history,
    upsert_history,
)
from yt_downloader.local_audio_video import LocalAudioVideoResult
from yt_downloader.models import (
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from yt_downloader.run_identity import matching_attempt
from yt_downloader.run_state import (
    RunRecoveryOwner,
    RunStateError,
    run_state_file_path,
    serialize_download_job,
)


class DownloadRuntime:
    def __init__(self) -> None:
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.history_path = history_file_path()
        self.history = load_history(self.history_path)
        self.recovery = RunRecoveryOwner(run_state_file_path())
        self.recovered, self.queued = self.recovery.startup_recovery()
        self.recovery_notice = self.recovery.recovery_notice
        if file_operations_pending(self.history_path) and self.recovery_notice is None:
            self.recovery_notice = (
                "Library file recovery must finish before new downloads."
            )
        self.worker: threading.Thread | None = None
        self.active_job: DownloadJob | None = None
        self._worker_app: DownloadWorkerCore | None = None
        self._closing = False
        self._history_error = False
        self.activity: list[dict[str, str]] = []
        for job in [*self.recovered, *self.queued]:
            self._activity_upsert(
                job,
                job.terminal_status or "Queued",
                job.terminal_message or "Waiting to resume",
            )
        set_active_child_process_observer(self.recovery.child_event)
        if self.queued and not self.recovery_notice:
            self._launch_next_queued()

    @property
    def busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def start(
        self,
        url: str,
        output_dir: Path,
        output_type: str,
        export_mode: str,
        quality_label: str = "1080p Full HD",
    ) -> DownloadJob:
        if self._closing:
            raise RuntimeError("VODForge is closing.")
        if self.recovery_notice:
            raise RunStateError(self.recovery_notice)
        if self.active_job is None and self.busy:
            raise RuntimeError("The previous download is finishing.")
        if self.active_job is None and self.queued:
            self._launch_next_queued()
        url = url.strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Enter a complete video URL.")
        source_error = single_video_url_requires_video_id_error(url)
        if source_error:
            raise ValueError(source_error)
        selected_type = OutputType(output_type)
        selected_mode = ExportMode(export_mode)
        validate_output_directory_access(output_dir)
        job = DownloadJob(
            url=url,
            urls=[url],
            output_dir=output_dir,
            output_type=selected_type,
            quality_label=quality_label,
            export_mode=selected_mode,
            manual_settings=ManualExportSettings(),
            mp3_settings=Mp3ExportSettings(),
            single_video_only=True,
            use_nvenc=False,
            embed_thumbnail=False,
            write_thumbnail=False,
            embed_metadata=True,
            write_info_json=False,
            tags=[],
        )
        active_and_queued = [
            *([self.active_job] if self.active_job is not None else []),
            *self.queued,
        ]
        if matching_attempt(job, active_and_queued):
            raise ValueError("This download is already active or queued.")
        if self.active_job is not None:
            pending = [*self.queued, job]
            self.recovery.queue_changed(pending)
            self.queued = pending
            self._activity_upsert(job, "Queued", "Waiting for the active download")
            return job
        self._launch(job)
        return job

    def _launch(self, job: DownloadJob) -> None:
        self.recovery.begin(job, self.queued)
        self._activity_upsert(job, "Running", "Preparing download")
        self._make_worker(job)

    def _launch_next_queued(self) -> None:
        if self.active_job is not None or not self.queued or self.recovery_notice:
            return
        job = self.queued[0]
        remaining = self.queued[1:]
        self.recovery.begin(job, remaining)
        self.queued = remaining
        self._activity_upsert(job, "Running", "Preparing download")
        self._make_worker(job)

    def _activity_upsert(self, job: DownloadJob, status: str, detail: str) -> None:
        title = str(
            (job.preview_info or {}).get("title") or f"{job.output_type.value} download"
        )
        entry = {
            "runId": job.run_id,
            "title": title[:300],
            "status": status,
            "detail": detail[:500],
        }
        self.activity = [
            entry,
            *[item for item in self.activity if item["runId"] != job.run_id],
        ][:100]

    def _make_worker(self, job: DownloadJob) -> None:
        # The production worker is now a UI-independent owner shared by Tk,
        # Qt, and the engineering harness.
        worker_app = DownloadWorkerCore()
        worker_app.events = self.events
        worker_app.cancel_requested = False
        worker_app.skip_video_requested = False
        worker_app.skip_url_requested = False
        worker_app._active_progress_context = None
        worker_app._last_progress_event_at = 0.0
        worker_app.video_output_dirs_by_id = {}
        worker_app.download_history = self.history
        worker_app.run_recovery = self.recovery
        worker_app._provider_network = ProviderNetworkCoordinator()
        self._worker_app = worker_app
        self._history_error = False
        self.active_job = job
        self.worker = threading.Thread(
            target=worker_app._download_worker,
            args=(job,),
            name="vodforge-qt-download",
            daemon=False,
        )
        self.worker.start()

    def cancel(self) -> None:
        if self._worker_app is not None:
            self._worker_app.cancel_requested = True

    def poll(self) -> list[tuple[str, Any]]:
        result: list[tuple[str, Any]] = []
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind, payload = event
            if kind == "history_record" and isinstance(payload, dict):
                try:
                    self._record_history(payload)
                except (HistoryError, OSError, ValueError):
                    self._history_error = True
                    result.append(
                        ("status", "Output saved, but Library history needs attention.")
                    )
            elif kind == "job_metadata" and isinstance(payload, dict):
                job = payload.get("job")
                info = payload.get("info")
                if job is self.active_job and isinstance(info, dict):
                    job.preview_info = info
                    self._activity_upsert(job, "Running", "Processing media")
            elif kind in {"done", "partial", "stopped", "error"}:
                if self._history_error and kind in {"done", "partial"}:
                    kind, payload = (
                        "partial",
                        "Output saved, but Library history could not be updated.",
                    )
                    event = kind, payload
                self._finish(kind, str(payload))
            result.append(event)
        if (
            self.active_job is None
            and self.queued
            and not self._closing
            and not self.busy
        ):
            self._launch_next_queued()
        return result

    def _record_history(self, payload: dict[str, Any]) -> None:
        job = payload.get("job")
        info = payload.get("info")
        output_dir = payload.get("output_dir")
        if job is not self.active_job or not isinstance(info, dict) or not output_dir:
            raise HistoryError("Stale or invalid download history event.")
        record_info = dict(info)
        record_info.pop("vodforge_preview_complete", None)
        record_info.pop("vodforge_preview_run_id", None)
        record_info["vodforge_run_id"] = job.run_id
        record_info["vodforge_run_activity"] = sanitize_run_activity(job.activity_lines)
        record_info[RETRY_JOB_METADATA_KEY] = serialize_download_job(job)
        from yt_downloader.archive_file_operations import reconcile_file_record_delta

        target = Path(output_dir)
        record_info.setdefault("vodforge_output_dir", str(target))
        reconciled = reconcile_file_record_delta(
            record_info, self.history, self.history_path.parent / "file-operations"
        )
        if reconciled is None:
            return
        target = Path(reconciled.get("vodforge_output_dir") or target)
        updated = upsert_history(
            self.history, reconciled, target, replace_missing_media=True
        )
        save_history(self.history_path, updated)
        self.history = updated

    def record_local_conversion(self, result: LocalAudioVideoResult) -> None:
        """Commit a completed local video through the same durable Library owner."""
        from yt_downloader.app import save_custom_cached_thumbnail_image

        metadata = dict(result.history_metadata)
        try:
            save_custom_cached_thumbnail_image(metadata, result.image_path)
        except (OSError, RuntimeError, ValueError):
            # The media and Library record remain valid without cached artwork.
            pass
        updated = upsert_history(
            self.history,
            metadata,
            result.output_path.parent,
            replace_missing_media=True,
        )
        save_history(self.history_path, updated)
        self.history = updated

    def _finish(self, kind: str, message: str) -> None:
        job = self.active_job
        if job is None:
            return
        status = {
            "done": "Completed",
            "partial": "Partial",
            "stopped": "Stopped",
            "error": "Failed",
        }[kind]
        self._activity_upsert(job, status, message)
        if status in {"Failed", "Stopped"}:
            self.recovery.terminal(status, message, activity_lines=job.activity_lines)
        if status not in {"Failed", "Stopped"}:
            self.recovery.finished(job.run_id, application_closing=self._closing)
        self.active_job = None
        self._worker_app = None

    def close(self) -> None:
        self._closing = True
        self.cancel()
        if self.worker is not None and self.worker.is_alive():
            self.worker.join(timeout=10)
        if not self.busy:
            set_active_child_process_observer(None)
