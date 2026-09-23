"""Qt-neutral adapter for the existing serialized download and history owners.

The worker remains the production worker. This adapter owns only thread/event
handoff and refuses new work when durable run or history recovery is blocked.
"""

from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from yt_downloader.app import (
    DownloadWorkerCore,
    ProviderNetworkCoordinator,
    retry_url_for_item,
    set_active_child_process_observer,
    single_video_url_requires_video_id_error,
    terminate_all_active_child_processes,
    validate_output_directory_access,
)
from yt_downloader.cookie_inputs import (
    cookie_inputs_for_source,
    windows_chromium_cookie_warning,
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
    CookieSource,
    DownloadJob,
    ExportMode,
    ManualExportSettings,
    Mp3ExportSettings,
    OutputType,
)
from yt_downloader.product_telemetry import product_output_kind
from yt_downloader.run_identity import matching_attempt
from yt_downloader.run_state import (
    RunRecoveryOwner,
    RunStateError,
    run_state_file_path,
    serialize_download_job,
)
from yt_downloader.telemetry_features import export_dimensions
from yt_downloader.youtube_access import COOKIE_BROWSER_VALUES


@dataclass(frozen=True, slots=True)
class DownloadPreferences:
    single_video_only: bool = True
    use_nvenc: bool = False
    embed_thumbnail: bool = False
    write_thumbnail: bool = True
    embed_metadata: bool = False
    write_info_json: bool = True


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
        self.product_telemetry: Any | None = None
        self.activity: list[dict[str, str]] = []
        for job in [*self.recovered, *self.queued]:
            self._activity_upsert(
                job,
                job.terminal_status or "Queued",
                job.terminal_message or "Waiting to resume",
            )
        set_active_child_process_observer(self.recovery.child_event)

    def resume_queued(self) -> None:
        """Resume only after the caller binds consent and operation observers."""
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
        preferences: DownloadPreferences | None = None,
        manual_settings: ManualExportSettings | None = None,
        mp3_settings: Mp3ExportSettings | None = None,
        *,
        urls: list[str] | None = None,
        batch_mode: bool = False,
        cookie_source: CookieSource = CookieSource.PUBLIC,
        cookie_file: Path | None = None,
        cookie_browser: str | None = None,
    ) -> DownloadJob:
        if self._closing:
            raise RuntimeError("VODForge is closing.")
        if self.recovery_notice:
            raise RunStateError(self.recovery_notice)
        if self.active_job is None and self.busy:
            raise RuntimeError("The previous download is finishing.")
        if self.active_job is None and self.queued:
            self._launch_next_queued()
        job = self.prepare_job(
            url,
            output_dir,
            output_type,
            export_mode,
            quality_label,
            preferences,
            manual_settings,
            mp3_settings,
            urls=urls,
            batch_mode=batch_mode,
            cookie_source=cookie_source,
            cookie_file=cookie_file,
            cookie_browser=cookie_browser,
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
            self._observe_run("run_queued", job)
            return job
        self._launch(job)
        return job

    def prepare_job(
        self,
        url: str,
        output_dir: Path,
        output_type: str,
        export_mode: str,
        quality_label: str = "1080p Full HD",
        preferences: DownloadPreferences | None = None,
        manual_settings: ManualExportSettings | None = None,
        mp3_settings: Mp3ExportSettings | None = None,
        *,
        urls: list[str] | None = None,
        batch_mode: bool = False,
        cookie_source: CookieSource = CookieSource.PUBLIC,
        cookie_file: Path | None = None,
        cookie_browser: str | None = None,
    ) -> DownloadJob:
        """Validate current Forge inputs without admitting a run."""
        preferences = preferences or DownloadPreferences()
        selected_urls = [item.strip() for item in (urls or [url]) if item.strip()]
        if not selected_urls:
            raise ValueError("Enter a complete video URL or load a URL list.")
        for item in selected_urls:
            parsed = urlparse(item)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Every URL must be a complete video URL.")
            if preferences.single_video_only:
                source_error = single_video_url_requires_video_id_error(item)
                if source_error:
                    raise ValueError(source_error)
        url = selected_urls[0]
        selected_type = OutputType(output_type)
        selected_mode = ExportMode(export_mode)
        use_cookies, selected_file, selected_browser = cookie_inputs_for_source(
            cookie_source, cookie_file, cookie_browser
        )
        if cookie_source is CookieSource.FILE and (
            selected_file is None or not selected_file.is_file()
        ):
            raise ValueError("Choose an existing YouTube cookies.txt file.")
        if cookie_source is CookieSource.BROWSER:
            if selected_browser not in COOKIE_BROWSER_VALUES.values():
                raise ValueError("Choose a browser profile for YouTube access.")
            warning = windows_chromium_cookie_warning(selected_browser)
            if warning:
                raise ValueError(warning)
        validate_output_directory_access(output_dir)
        job = DownloadJob(
            url=url,
            urls=selected_urls,
            output_dir=output_dir,
            output_type=selected_type,
            quality_label=quality_label,
            export_mode=selected_mode,
            manual_settings=manual_settings or ManualExportSettings()
            if selected_type == OutputType.MP4
            and selected_mode == ExportMode.MANUAL_OVERRIDE
            else ManualExportSettings(),
            mp3_settings=mp3_settings or Mp3ExportSettings()
            if selected_type == OutputType.MP3
            else Mp3ExportSettings(),
            single_video_only=preferences.single_video_only,
            batch_mode=batch_mode,
            use_cookies=use_cookies,
            cookie_file=selected_file,
            cookie_browser=selected_browser,
            use_nvenc=preferences.use_nvenc
            if selected_type == OutputType.MP4
            else False,
            embed_thumbnail=preferences.embed_thumbnail
            if selected_type == OutputType.MP4
            else False,
            write_thumbnail=preferences.write_thumbnail
            if selected_type == OutputType.MP4
            else False,
            embed_metadata=preferences.embed_metadata
            if selected_type == OutputType.MP4
            else False,
            write_info_json=preferences.write_info_json
            if selected_type == OutputType.MP4
            else False,
            tags=[],
        )
        return job

    def _launch(self, job: DownloadJob) -> None:
        self.recovery.begin(job, self.queued)
        self._activity_upsert(job, "Running", "Preparing download")
        self._make_worker(job)
        self._observe_run("run_started", job)

    def terminal_retry_source(self, run_id: str) -> tuple[str, str]:
        """Resolve a single durable terminal source for the view's settings choice."""
        matches = [job for job in self.recovered if job.run_id == run_id]
        if len(matches) != 1 or matches[0].terminal_status not in {
            "Failed",
            "Stopped",
            "Skipped",
        }:
            raise ValueError("That saved run is no longer available to retry.")
        previous = matches[0]
        url = retry_url_for_item(previous.preview_info or {}, previous.url)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("This run has no usable source link. Paste it in Forge.")
        assert previous.terminal_status is not None
        return previous.terminal_status, url

    def retry_terminal(
        self, run_id: str, *, current_job: DownloadJob | None = None
    ) -> DownloadJob:
        """Admit one saved terminal attempt through the existing durable run owner."""
        if self._closing or self.recovery_notice:
            raise RunStateError("Run recovery needs attention before retrying.")
        if self.active_job is None and self.busy:
            raise RuntimeError("The previous download is finishing.")
        status, url = self.terminal_retry_source(run_id)
        previous = next(job for job in self.recovered if job.run_id == run_id)
        if status == "Failed":
            if (
                current_job is None
                or current_job.url != url
                or current_job.urls != [url]
            ):
                raise ValueError("Review current Forge settings before retrying.")
            settings_job = current_job
        else:
            settings_job = previous
            validate_output_directory_access(previous.output_dir)
        preview = dict(previous.preview_info or {})
        for key in (
            "vodforge_active_run_id",
            "vodforge_queued_run_id",
            "vodforge_run_status",
            "vodforge_terminal_status",
            "vodforge_terminal_message",
            "vodforge_terminal_run_id",
        ):
            preview.pop(key, None)
        retry = replace(
            settings_job,
            url=url,
            urls=[url],
            run_id=uuid.uuid4().hex,
            origin_run_id=previous.run_id,
            retry_of_run_id=previous.execution_run_id or previous.run_id,
            execution_run_id=None,
            preview_source_owner=None,
            annotation_source_owner=previous.annotation_source_owner,
            admission_observer=None,
            preview_info=preview,
            metadata_keys=set(),
            history_identities=set(),
            history_archive_owners=set(),
            activity_lines=[],
            terminal_status=None,
            terminal_message="",
            failure_diagnostic=None,
            item_terminal_emitted=False,
        )
        if matching_attempt(
            retry,
            [
                *([self.active_job] if self.active_job is not None else []),
                *self.queued,
            ],
        ):
            raise ValueError("This download is already active or queued.")
        if self.active_job is None and self.queued:
            self._launch_next_queued()
        if self.active_job is not None or self.busy:
            pending = [*self.queued, retry]
            self.recovery.queue_changed(pending, superseded_run_id=previous.run_id)
            self.queued = pending
            self._activity_upsert(retry, "Queued", "Waiting for the active download")
            self._observe_run("run_queued", retry)
        else:
            self.recovery.begin(retry, self.queued, superseded_run_id=previous.run_id)
            self._activity_upsert(retry, "Running", "Preparing download")
            self._make_worker(retry)
            self._observe_run("run_started", retry)
        self.recovered = [
            job for job in self.recovered if job.run_id != previous.run_id
        ]
        self.activity = [
            item for item in self.activity if item["runId"] != previous.run_id
        ]
        return retry

    def _launch_next_queued(self) -> None:
        if self.active_job is not None or not self.queued or self.recovery_notice:
            return
        job = self.queued[0]
        remaining = self.queued[1:]
        self.recovery.begin(job, remaining)
        self.queued = remaining
        self._activity_upsert(job, "Running", "Preparing download")
        self._make_worker(job)
        self._observe_run("run_started", job)

    def _observe_run(
        self, event_name: str, job: DownloadJob, *, status: str = ""
    ) -> None:
        telemetry = self.product_telemetry
        if telemetry is None:
            return
        dimensions = export_dimensions(job)
        if status:
            dimensions["outcome"] = {
                "Completed": "complete",
                "Partial": "partial",
                "Failed": "failed",
                "Stopped": "stopped",
            }[status]
        try:
            telemetry.record(
                event_name,
                dedupe_key=job.run_id,
                attempt_key=job.run_id,
                retry_key=job.retry_of_run_id,
                dimensions=dimensions,
                run_kind="youtube",
                output_type=product_output_kind(job.output_type.value),
                failure_reason=(
                    job.failure_diagnostic.reason
                    if event_name == "run_failed" and job.failure_diagnostic
                    else None
                ),
                failure_detail=(
                    job.failure_diagnostic.payload()
                    if event_name == "run_failed" and job.failure_diagnostic
                    else None
                ),
            )
        except (OSError, ValueError):
            # Optional observation cannot change the durable run outcome.
            pass

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
        worker_app.product_telemetry = self.product_telemetry
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
            threading.Thread(
                target=terminate_all_active_child_processes,
                name="vodforge-qt-stop-children",
                daemon=True,
            ).start()

    def skip_item(self) -> None:
        if self._worker_app is not None:
            self._worker_app.skip_video_requested = True
            threading.Thread(
                target=terminate_all_active_child_processes,
                name="vodforge-qt-skip-item-children",
                daemon=True,
            ).start()

    def skip_source(self) -> None:
        if self._worker_app is not None:
            self._worker_app.skip_url_requested = True
            self._worker_app.skip_video_requested = True
            threading.Thread(
                target=terminate_all_active_child_processes,
                name="vodforge-qt-skip-source-children",
                daemon=True,
            ).start()

    def remove_queued(self, run_id: str) -> bool:
        matches = [job for job in self.queued if job.run_id == run_id]
        if len(matches) != 1:
            return False
        remaining = [job for job in self.queued if job.run_id != run_id]
        self.recovery.queue_changed(remaining)
        self.queued = remaining
        self._observe_run("run_dequeued", matches[0])
        self._activity_upsert(matches[0], "Removed", "Removed from the queue")
        return True

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
            elif kind == "job_log" and isinstance(payload, dict):
                job = payload.get("job")
                active = self.active_job
                if (
                    isinstance(job, DownloadJob)
                    and active is not None
                    and job.run_id == active.run_id
                ):
                    line = str(payload.get("line") or "").rstrip()
                    active.activity_lines.append(line)
                    result.append(("log", line))
                continue
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
        active = self.active_job
        same_batch_child = (
            isinstance(job, DownloadJob)
            and active is not None
            and active.batch_mode
            and job.run_id == active.run_id
            and job.url in active.urls
            and job.urls == [job.url]
            and job.output_dir == active.output_dir
            and job.output_type == active.output_type
        )
        if (
            not (job is active or same_batch_child)
            or not isinstance(info, dict)
            or not output_dir
        ):
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
        self._observe_run(
            "run_completed"
            if status in {"Completed", "Partial"}
            else "run_stopped"
            if status == "Stopped"
            else "run_failed",
            job,
            status=status,
        )
        self._activity_upsert(job, status, message)
        if status in {"Failed", "Stopped"}:
            self.recovery.terminal(status, message, activity_lines=job.activity_lines)
            self.recovered = self.recovery.store.load_terminal_jobs()
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
