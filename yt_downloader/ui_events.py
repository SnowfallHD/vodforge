from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from tkinter import messagebox
from typing import Any, Literal, Protocol, TypeAlias, TypedDict

from .cloud_funnel import (
    InstallationIdentityError,
    InstallationState,
    mark_cloud_seen_confirmed,
    mark_first_launch_confirmed,
)
from .models import DownloadJob
from .run_identity import annotate_job_metadata
from .updates import MacUpdatePlan, ReleaseInfo


class JobLogPayload(TypedDict):
    job: DownloadJob
    line: str


class JobInfoPayload(TypedDict):
    job: DownloadJob
    info: dict[str, Any]


class HistoryRecordPayload(JobInfoPayload):
    output_dir: str


class ThumbnailPreviewPayload(TypedDict, total=False):
    id: int
    url: str
    target: str
    run_id: str
    data: bytes
    error: str


class InstallationResultPayload(TypedDict):
    success: bool
    install_id: str


JobInfoEventName: TypeAlias = Literal[
    "job_metadata",
    "queued_preview",
    "item_terminal",
]


TransferUiEvent: TypeAlias = (
    tuple[Literal["log", "status"], str]
    | tuple[Literal["job_log"], JobLogPayload]
    | tuple[Literal["progress"], int | float]
    | tuple[Literal["progress_determinate"], int | float | None]
    | tuple[
        Literal["progress_indeterminate_start", "progress_indeterminate_stop"],
        None,
    ]
)
MetadataUiEvent: TypeAlias = (
    tuple[Literal["metadata"], dict[str, Any]]
    | tuple[Literal["job_metadata", "queued_preview", "item_terminal"], JobInfoPayload]
    | tuple[Literal["history_record"], HistoryRecordPayload]
    | tuple[Literal["thumbnail_preview_result"], ThumbnailPreviewPayload]
)
RuntimeUiEvent: TypeAlias = (
    tuple[Literal["metadata_fetch_done"], None]
    | tuple[Literal["metadata_error", "runtime_error", "update_check_error"], str]
    | tuple[Literal["download_folders"], list[Path]]
    | tuple[Literal["update_check_result"], ReleaseInfo]
    | tuple[Literal["update_ready"], Path | MacUpdatePlan]
    | tuple[
        Literal["cloud_seen_result", "first_launch_result"],
        InstallationResultPayload,
    ]
)
TerminalUiEvent: TypeAlias = tuple[
    Literal["done", "partial", "stopped", "error"],
    str,
]
UiEvent: TypeAlias = (
    TransferUiEvent | MetadataUiEvent | RuntimeUiEvent | TerminalUiEvent
)


def job_log_event(
    job: DownloadJob, line: str
) -> tuple[Literal["job_log"], JobLogPayload]:
    return "job_log", {"job": job, "line": line}


def job_info_event(
    name: JobInfoEventName,
    job: DownloadJob,
    info: dict[str, Any],
) -> tuple[JobInfoEventName, JobInfoPayload]:
    return name, {"job": job, "info": annotate_job_metadata(job, info)}


def history_record_event(
    job: DownloadJob,
    info: dict[str, Any],
    output_dir: str,
) -> tuple[Literal["history_record"], HistoryRecordPayload]:
    return "history_record", {
        "job": job,
        "info": annotate_job_metadata(job, info),
        "output_dir": output_dir,
    }


def thumbnail_preview_event(
    request_id: int,
    url: str,
    target: str,
    run_id: str,
    *,
    data: bytes | None = None,
    error: str | None = None,
) -> tuple[Literal["thumbnail_preview_result"], ThumbnailPreviewPayload]:
    payload: ThumbnailPreviewPayload = {
        "id": request_id,
        "url": url,
        "target": target,
        "run_id": run_id,
    }
    if data is not None:
        payload["data"] = data
    if error is not None:
        payload["error"] = error
    return "thumbnail_preview_result", payload


def installation_result_event(
    name: Literal["cloud_seen_result", "first_launch_result"],
    success: bool,
    install_id: str,
) -> tuple[
    Literal["cloud_seen_result", "first_launch_result"],
    InstallationResultPayload,
]:
    return name, {"success": success, "install_id": install_id}


class UiEventSink(Protocol):
    """Minimal FIFO producer contract shared by Queue and harness tracing sinks."""

    def put(self, event: UiEvent) -> None: ...


class _FloatVariable(Protocol):
    def get(self) -> float: ...

    def set(self, value: float) -> None: ...


class _StringVariable(Protocol):
    def get(self) -> str: ...

    def set(self, value: str) -> None: ...


class _ConfigurableControl(Protocol):
    @property
    def config(self) -> Callable[..., Any]: ...


class _UiEventHost(Protocol):
    """Structural host surface required by the UI event dispatcher."""

    _event_app_name: str
    _event_subtle_color: str
    last_output_dirs: list[Path]
    update_check_silent: bool
    installation_state: InstallationState | None

    @property
    def progress_var(self) -> _FloatVariable: ...

    @property
    def status_var(self) -> _StringVariable: ...

    @property
    def pending_jobs(self) -> Sequence[DownloadJob]: ...

    @property
    def active_job(self) -> DownloadJob | None: ...

    @property
    def installation_state_path(self) -> Path: ...

    @property
    def download_button(self) -> _ConfigurableControl: ...

    @property
    def cancel_button(self) -> _ConfigurableControl: ...

    @property
    def skip_video_button(self) -> _ConfigurableControl: ...

    @property
    def skip_url_button(self) -> _ConfigurableControl: ...

    @property
    def update_button(self) -> _ConfigurableControl: ...

    @property
    def _focus_selected_run_id(self) -> str | None: ...

    @property
    def focus_transfer_var(self) -> _StringVariable: ...

    @property
    def focus_run_status_var(self) -> _StringVariable: ...

    @property
    def focus_percent_var(self) -> _StringVariable: ...

    def _event_write_diagnostic(self, message: str) -> None: ...

    def _handle_transfer_event(self, kind: str, payload: Any) -> bool: ...

    def _handle_metadata_event(self, kind: str, payload: Any) -> bool: ...

    def _handle_runtime_event(self, kind: str, payload: Any) -> bool: ...

    def _handle_terminal_event(self, kind: str, payload: Any) -> bool: ...

    def _append_log(self, line: str) -> None: ...

    def _append_job_log(self, event_job: DownloadJob, line: str) -> None: ...

    def _display_metadata(
        self,
        info: dict[str, Any],
        *,
        active_job: DownloadJob | None = None,
        preview_complete: bool = False,
    ) -> None: ...

    def _active_run_for_metadata_event(
        self,
        event_job: DownloadJob,
    ) -> DownloadJob | None: ...

    def _display_thumbnail_preview_result(self, payload: dict[str, Any]) -> None: ...

    def _refresh_focus_run_deck(self) -> None: ...

    def _focus_run_records(self) -> list[dict[str, Any]]: ...

    def _display_focus_queued_job_snapshot(
        self,
        record: dict[str, Any],
        job: DownloadJob,
    ) -> None: ...

    def _project_queued_job_to_library(
        self,
        job: DownloadJob,
        info: dict[str, Any] | None = None,
    ) -> None: ...

    def _update_active_library_status(self, status_text: str) -> None: ...

    def _library_run_is_suppressed(self, job: DownloadJob | None) -> bool: ...

    def _record_download_history(
        self,
        info: dict[str, Any],
        output_dir: Path,
        *,
        owning_job: DownloadJob | None = None,
    ) -> None: ...

    def _archive_item_terminal_job(
        self,
        job: DownloadJob,
        info: dict[str, Any],
    ) -> None: ...

    def _display_metadata_preview_request(self, record: dict[str, Any]) -> None: ...

    def _show_update_result(self, release: ReleaseInfo) -> None: ...

    def _install_downloaded_update(self, update: Path | MacUpdatePlan) -> None: ...

    def _schedule_auto_update_check(self, delay_ms: int = ...) -> None: ...

    def _set_focus_update_state(self, text: str, color: str) -> None: ...

    def _finish_run_ui(
        self,
        message: str,
        run_status: str,
        transfer_text: str,
        *,
        progress: float | None = None,
    ) -> None: ...

    def _archive_active_terminal_job(self, status: str, message: str) -> None: ...

    def _focus_follows_active_run(self) -> bool: ...

    def _launch_next_pending_job(self) -> bool: ...

    def _set_focus_run_controls_visible(self, visible: bool) -> None: ...

    def _focus_terminal_job(self, job: DownloadJob) -> None: ...


class UiEventHandlersMixin:
    """UI-thread handlers for worker and application lifecycle events."""

    _event_app_name: str
    _event_subtle_color: str
    installation_state: InstallationState | None

    def _event_write_diagnostic(self, message: str) -> None:
        raise NotImplementedError

    def _dispatch_ui_event(self: _UiEventHost, event: UiEvent) -> None:
        """Dispatch one FIFO event while preserving worker-to-UI ownership rules."""
        kind, payload = event
        if kind in {
            "progress_indeterminate_start",
            "progress_indeterminate_stop",
            "progress_determinate",
            "progress",
            "status",
        } and self._library_run_is_suppressed(self.active_job):
            return
        if self._handle_transfer_event(kind, payload):
            return
        if self._handle_metadata_event(kind, payload):
            return
        if self._handle_runtime_event(kind, payload):
            return
        self._handle_terminal_event(kind, payload)

    def _handle_transfer_event(
        self: _UiEventHost,
        kind: str,
        payload: Any,
    ) -> bool:
        if kind == "log":
            self._append_log(str(payload))
        elif kind == "job_log":
            if isinstance(payload, dict) and isinstance(
                payload.get("job"), DownloadJob
            ):
                self._append_job_log(payload["job"], str(payload.get("line") or ""))
        elif kind == "progress_indeterminate_start":
            if hasattr(self, "progress_bar"):
                self.progress_bar.stop()
                self.progress_bar.config(mode="indeterminate")
                self.progress_bar.start(50)
        elif kind in {"progress_indeterminate_stop", "progress_determinate"}:
            if hasattr(self, "progress_bar"):
                self.progress_bar.stop()
                self.progress_bar.config(mode="determinate")
            if payload is not None:
                self.progress_var.set(float(payload))
        elif kind == "progress":
            if hasattr(self, "progress_bar"):
                self.progress_bar.stop()
                self.progress_bar.config(mode="determinate")
            self.progress_var.set(float(payload))
        elif kind == "status":
            status_text = str(payload)
            self.status_var.set(status_text)
            self._update_active_library_status(status_text)
            if hasattr(self, "focus_run_status_var"):
                eta = status_text.partition(" ETA ")[2]
                if eta:
                    self.focus_run_status_var.set(
                        f"{self.progress_var.get():.0f}%  /  ETA {eta}"
                    )
        else:
            return False
        return True

    def _handle_metadata_event(
        self: _UiEventHost,
        kind: str,
        payload: Any,
    ) -> bool:
        if kind == "metadata":
            UiEventHandlersMixin._handle_metadata(self, payload)
        elif kind == "job_metadata":
            UiEventHandlersMixin._handle_job_metadata(self, payload)
        elif kind == "thumbnail_preview_result":
            UiEventHandlersMixin._handle_thumbnail_preview_result(self, payload)
        elif kind == "queued_preview":
            UiEventHandlersMixin._handle_queued_preview(self, payload)
        elif kind == "history_record":
            UiEventHandlersMixin._handle_history_record(self, payload)
        elif kind == "item_terminal":
            UiEventHandlersMixin._handle_item_terminal(self, payload)
        else:
            return False
        return True

    def _handle_metadata(self: _UiEventHost, payload: Any) -> None:
        if isinstance(payload, dict):
            self._display_metadata(payload, preview_complete=True)

    def _handle_job_metadata(self: _UiEventHost, payload: Any) -> None:
        if not (
            isinstance(payload, dict)
            and isinstance(payload.get("job"), DownloadJob)
            and isinstance(payload.get("info"), dict)
        ):
            return
        metadata_job = payload["job"]
        active_metadata_job = self._active_run_for_metadata_event(metadata_job)
        if active_metadata_job is not None:
            self._display_metadata(payload["info"], active_job=active_metadata_job)
        else:
            self._event_write_diagnostic(
                f"ignored stale run metadata event for run_id={metadata_job.run_id}"
            )

    def _handle_thumbnail_preview_result(
        self: _UiEventHost,
        payload: Any,
    ) -> None:
        if isinstance(payload, dict):
            self._display_thumbnail_preview_result(payload)

    def _handle_queued_preview(self: _UiEventHost, payload: Any) -> None:
        if not (
            isinstance(payload, dict)
            and isinstance(payload.get("job"), DownloadJob)
            and isinstance(payload.get("info"), dict)
        ):
            return
        queued_job = payload["job"]
        if not any(item is queued_job for item in self.pending_jobs):
            return
        queued_job.preview_info = dict(payload["info"])
        self._project_queued_job_to_library(queued_job, payload["info"])
        if hasattr(self, "focus_run_deck"):
            self._refresh_focus_run_deck()
        if self._focus_selected_run_id != queued_job.run_id:
            return
        record = next(
            (
                candidate
                for candidate in self._focus_run_records()
                if candidate.get("run_id") == queued_job.run_id
            ),
            None,
        )
        if record is not None:
            self._display_focus_queued_job_snapshot(record, queued_job)

    def _handle_history_record(self: _UiEventHost, payload: Any) -> None:
        if not (isinstance(payload, dict) and isinstance(payload.get("info"), dict)):
            return
        output_dir = str(payload.get("output_dir") or "").strip()
        if not output_dir:
            return
        history_job = payload.get("job")
        if isinstance(history_job, DownloadJob) and self._library_run_is_suppressed(
            history_job
        ):
            self._event_write_diagnostic(
                f"ignored history event for Library-removed run_id={history_job.run_id}"
            )
            return
        owning_job = (
            self._active_run_for_metadata_event(history_job)
            if isinstance(history_job, DownloadJob)
            else None
        )
        self._record_download_history(
            payload["info"],
            Path(output_dir),
            owning_job=owning_job,
        )

    def _handle_item_terminal(self: _UiEventHost, payload: Any) -> None:
        if not (
            isinstance(payload, dict)
            and isinstance(payload.get("job"), DownloadJob)
            and isinstance(payload.get("info"), dict)
        ):
            return
        terminal_job = payload["job"]
        if not self._library_run_is_suppressed(terminal_job):
            self._archive_item_terminal_job(terminal_job, payload["info"])

    def _handle_runtime_event(
        self: _UiEventHost,
        kind: str,
        payload: Any,
    ) -> bool:
        if kind == "metadata_fetch_done":
            UiEventHandlersMixin._handle_metadata_fetch_done(self)
        elif kind == "metadata_error":
            UiEventHandlersMixin._handle_metadata_error(self, payload)
        elif kind == "runtime_error":
            UiEventHandlersMixin._handle_runtime_error(self, payload)
        elif kind == "download_folders":
            UiEventHandlersMixin._handle_download_folders(self, payload)
        elif kind == "update_check_result":
            UiEventHandlersMixin._handle_update_check_result(self, payload)
        elif kind == "update_ready":
            UiEventHandlersMixin._handle_update_ready(self, payload)
        elif kind == "update_check_error":
            UiEventHandlersMixin._handle_update_check_error(self, payload)
        elif kind == "cloud_seen_result":
            UiEventHandlersMixin._handle_cloud_seen_result(self, payload)
        elif kind == "first_launch_result":
            UiEventHandlersMixin._handle_first_launch_result(self, payload)
        else:
            return False
        return True

    def _handle_metadata_fetch_done(self: _UiEventHost) -> None:
        if hasattr(self, "preview_metadata_button"):
            self.preview_metadata_button.config(state="normal")

    def _handle_metadata_error(self: _UiEventHost, payload: Any) -> None:
        if self.__dict__.get("_closing", False):
            self._append_log(
                f"Metadata preview ended during application close: {payload}"
            )
            return
        preview_request = self.__dict__.get("_metadata_preview_request")
        if isinstance(preview_request, dict):
            preview_request.update(
                {
                    "title": "Preview failed",
                    "status": "Preview failed  •  "
                    f"{preview_request.get('output_type') or 'MP4'}",
                    "kind": "preview_failed",
                    "message": str(payload),
                }
            )
            self._refresh_focus_run_deck()
            if self.__dict__.get("_focus_selected_run_id") == preview_request.get(
                "run_id"
            ):
                self._display_metadata_preview_request(preview_request)
        self.status_var.set("Metadata preview failed")
        self._append_log(f"ERROR: {payload}")
        messagebox.showerror(self._event_app_name, str(payload))

    def _handle_runtime_error(self: _UiEventHost, payload: Any) -> None:
        self._append_log(f"ERROR: {payload}")
        self.download_button.config(state="disabled")

    def _handle_download_folders(self: _UiEventHost, payload: Any) -> None:
        if isinstance(payload, list):
            self.last_output_dirs = [Path(path) for path in payload]

    def _handle_update_check_result(self: _UiEventHost, payload: Any) -> None:
        if not self.__dict__.get("_closing", False) and isinstance(
            payload, ReleaseInfo
        ):
            self._show_update_result(payload)

    def _handle_update_ready(self: _UiEventHost, payload: Any) -> None:
        if not self.__dict__.get("_closing", False) and isinstance(
            payload, (Path, MacUpdatePlan)
        ):
            self._install_downloaded_update(payload)

    def _handle_update_check_error(self: _UiEventHost, payload: Any) -> None:
        if self.__dict__.get("_closing", False):
            self._event_write_diagnostic(
                f"update check ended during application close: {payload}"
            )
            return
        silent = self.update_check_silent
        self.update_check_silent = False
        self._schedule_auto_update_check()
        self.update_button.config(state="normal")
        self._set_focus_update_state("Check updates", self._event_subtle_color)
        if silent:
            self._event_write_diagnostic(f"automatic update check failed: {payload}")
        else:
            self.status_var.set("Could not check for updates.")
            messagebox.showinfo(self._event_app_name, str(payload))

    def _handle_cloud_seen_result(self: _UiEventHost, payload: Any) -> None:
        if not (isinstance(payload, dict) and payload.get("success") is True):
            return
        state = self.installation_state
        install_id = str(payload.get("install_id") or "")
        if state is None or install_id != state.install_id:
            return
        try:
            self.installation_state = mark_cloud_seen_confirmed(
                self.installation_state_path,
                install_id,
            )
            self._event_write_diagnostic(
                "Cloud early-access impression confirmed once for this installation"
            )
        except (InstallationIdentityError, OSError) as exc:
            self._event_write_diagnostic(
                "Cloud impression was accepted but local confirmation "
                f"could not be saved: {exc}"
            )

    def _handle_first_launch_result(self: _UiEventHost, payload: Any) -> None:
        if not (isinstance(payload, dict) and payload.get("success") is True):
            return
        state = self.installation_state
        install_id = str(payload.get("install_id") or "")
        if state is None or install_id != state.install_id:
            return
        try:
            self.installation_state = mark_first_launch_confirmed(
                self.installation_state_path,
                install_id,
            )
            self._event_write_diagnostic(
                "first successful launch confirmed once for this installation"
            )
        except (InstallationIdentityError, OSError) as exc:
            self._event_write_diagnostic(
                "first launch was accepted but local confirmation "
                f"could not be saved: {exc}"
            )

    def _handle_terminal_event(
        self: _UiEventHost,
        kind: str,
        payload: Any,
    ) -> bool:
        if kind == "done":
            UiEventHandlersMixin._handle_done_terminal(self, payload)
        elif kind == "partial":
            UiEventHandlersMixin._handle_partial_terminal(self, payload)
        elif kind == "stopped":
            UiEventHandlersMixin._handle_stopped_terminal(self, payload)
        elif kind == "error":
            UiEventHandlersMixin._handle_error_terminal(self, payload)
        else:
            return False
        return True

    def _handle_done_terminal(self: _UiEventHost, payload: Any) -> None:
        self._finish_run_ui(
            str(payload),
            "Completed",
            "Complete  /  Ready to open in Library",
            progress=100,
        )

    def _handle_partial_terminal(self: _UiEventHost, payload: Any) -> None:
        self._finish_run_ui(
            str(payload),
            "Partial",
            "Completed with issues  /  Valid files are in Library",
            progress=100,
        )

    def _handle_stopped_terminal(self: _UiEventHost, payload: Any) -> None:
        self._finish_run_ui(
            str(payload),
            "Stopped",
            "Stopped  /  No incomplete output was committed",
        )

    def _handle_error_terminal(self: _UiEventHost, payload: Any) -> None:
        if self.__dict__.get("_closing", False):
            self._append_log(f"ERROR during application close: {payload}")
            return
        failed_job = self.active_job
        if self._library_run_is_suppressed(failed_job):
            self._finish_run_ui(
                "Removed from Library; the run was stopped.",
                "Stopped",
                "Stopped  /  Removed from Library",
            )
            return
        if failed_job is not None:
            self._append_job_log(failed_job, f"ERROR: {payload}")
        else:
            self._append_log(f"ERROR: {payload}")
        self._archive_active_terminal_job("Failed", str(payload))
        self.progress_var.set(0)
        self.status_var.set("Failed")
        messagebox.showerror(self._event_app_name, str(payload))
        self.download_button.config(state="normal")
        self.cancel_button.config(state="disabled")
        self.skip_video_button.config(state="disabled")
        self.skip_url_button.config(state="disabled")
        if hasattr(self, "focus_transfer_var"):
            if self._focus_follows_active_run():
                self.focus_transfer_var.set(
                    "Run failed  /  Review Activity for details"
                )
            self.focus_run_status_var.set("Failed")
            if self._focus_follows_active_run():
                self.focus_percent_var.set("Failed")
            self._refresh_focus_run_deck()
        if not self._launch_next_pending_job() and hasattr(self, "focus_transfer_var"):
            self._set_focus_run_controls_visible(False)
            self._refresh_focus_run_deck()
        if failed_job is not None:
            self._focus_terminal_job(failed_job)
