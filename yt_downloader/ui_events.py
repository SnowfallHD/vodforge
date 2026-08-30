from __future__ import annotations

from pathlib import Path
from tkinter import messagebox
from typing import Any

from .cloud_funnel import (
    InstallationIdentityError,
    mark_cloud_seen_confirmed,
    mark_first_launch_confirmed,
)
from .models import DownloadJob
from .updates import MacUpdatePlan, ReleaseInfo


class UiEventHandlersMixin:
    """UI-thread handlers for worker and application lifecycle events."""

    _event_app_name: str
    _event_subtle_color: str

    def _event_write_diagnostic(self, message: str) -> None:
        raise NotImplementedError

    def _handle_transfer_event(self, kind: str, payload: Any) -> bool:
        if kind == "log":
            self._append_log(str(payload))
        elif kind == "job_log":
            if isinstance(payload, dict) and isinstance(payload.get("job"), DownloadJob):
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
            self.status_var.set(str(payload))
            if hasattr(self, "focus_run_status_var"):
                status_text = str(payload)
                eta = status_text.partition(" ETA ")[2]
                if eta:
                    self.focus_run_status_var.set(
                        f"{self.progress_var.get():.0f}%  /  ETA {eta}"
                    )
        else:
            return False
        return True

    def _handle_metadata_event(self, kind: str, payload: Any) -> bool:
        if kind == "metadata":
            if isinstance(payload, dict):
                self._display_metadata(payload, preview_complete=True)
        elif kind == "job_metadata":
            if (
                isinstance(payload, dict)
                and isinstance(payload.get("job"), DownloadJob)
                and isinstance(payload.get("info"), dict)
            ):
                metadata_job = payload["job"]
                active_metadata_job = self._active_run_for_metadata_event(metadata_job)
                if active_metadata_job is not None:
                    self._display_metadata(payload["info"], active_job=active_metadata_job)
                else:
                    self._event_write_diagnostic(
                        f"ignored stale run metadata event for run_id={metadata_job.run_id}"
                    )
        elif kind == "thumbnail_preview_result":
            if isinstance(payload, dict):
                self._display_thumbnail_preview_result(payload)
        elif kind == "queued_preview":
            if (
                isinstance(payload, dict)
                and isinstance(payload.get("job"), DownloadJob)
                and isinstance(payload.get("info"), dict)
            ):
                queued_job = payload["job"]
                if any(item is queued_job for item in self.pending_jobs):
                    queued_job.preview_info = dict(payload["info"])
                    if hasattr(self, "focus_run_deck"):
                        self._refresh_focus_run_deck()
                    if self._focus_selected_run_id == queued_job.run_id:
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
        elif kind == "history_record":
            if isinstance(payload, dict) and isinstance(payload.get("info"), dict):
                output_dir = str(payload.get("output_dir") or "").strip()
                if output_dir:
                    history_job = payload.get("job")
                    if isinstance(
                        history_job, DownloadJob
                    ) and self._library_run_is_suppressed(history_job):
                        self._event_write_diagnostic(
                            "ignored history event for Library-removed "
                            f"run_id={history_job.run_id}"
                        )
                        return True
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
        elif kind == "item_terminal":
            if (
                isinstance(payload, dict)
                and isinstance(payload.get("job"), DownloadJob)
                and isinstance(payload.get("info"), dict)
            ):
                terminal_job = payload["job"]
                if not self._library_run_is_suppressed(terminal_job):
                    self._archive_item_terminal_job(terminal_job, payload["info"])
        else:
            return False
        return True

    def _handle_runtime_event(self, kind: str, payload: Any) -> bool:
        if kind == "metadata_fetch_done":
            if hasattr(self, "preview_metadata_button"):
                self.preview_metadata_button.config(state="normal")
        elif kind == "metadata_error":
            if self.__dict__.get("_closing", False):
                self._append_log(
                    f"Metadata preview ended during application close: {payload}"
                )
            else:
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
                    if self.__dict__.get(
                        "_focus_selected_run_id"
                    ) == preview_request.get("run_id"):
                        self._display_metadata_preview_request(preview_request)
                self.status_var.set("Metadata preview failed")
                self._append_log(f"ERROR: {payload}")
                messagebox.showerror(self._event_app_name, str(payload))
        elif kind == "runtime_error":
            self._append_log(f"ERROR: {payload}")
            self.download_button.config(state="disabled")
        elif kind == "download_folders":
            if isinstance(payload, list):
                self.last_output_dirs = [Path(path) for path in payload]
        elif kind == "update_check_result":
            if not self.__dict__.get("_closing", False) and isinstance(
                payload, ReleaseInfo
            ):
                self._show_update_result(payload)
        elif kind == "update_ready":
            if not self.__dict__.get("_closing", False) and isinstance(
                payload, (Path, MacUpdatePlan)
            ):
                self._install_downloaded_update(payload)
        elif kind == "update_check_error":
            if self.__dict__.get("_closing", False):
                self._event_write_diagnostic(
                    f"update check ended during application close: {payload}"
                )
                return True
            silent = self.update_check_silent
            self.update_check_silent = False
            self._schedule_auto_update_check()
            self.update_button.config(state="normal")
            self._set_focus_update_state("Check updates", self._event_subtle_color)
            if silent:
                self._event_write_diagnostic(
                    f"automatic update check failed: {payload}"
                )
            else:
                self.status_var.set("Could not check for updates.")
                messagebox.showinfo(self._event_app_name, str(payload))
        elif kind == "cloud_seen_result":
            if isinstance(payload, dict) and payload.get("success") is True:
                state = self.installation_state
                install_id = str(payload.get("install_id") or "")
                if state is not None and install_id == state.install_id:
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
        elif kind == "first_launch_result":
            if isinstance(payload, dict) and payload.get("success") is True:
                state = self.installation_state
                install_id = str(payload.get("install_id") or "")
                if state is not None and install_id == state.install_id:
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
        else:
            return False
        return True

    def _handle_terminal_event(self, kind: str, payload: Any) -> bool:
        if kind == "done":
            self._finish_run_ui(
                str(payload),
                "Completed",
                "Complete  /  Ready to open in Library",
                progress=100,
            )
        elif kind == "partial":
            self._finish_run_ui(
                str(payload),
                "Partial",
                "Completed with issues  /  Valid files are in Library",
                progress=100,
            )
        elif kind == "stopped":
            self._finish_run_ui(
                str(payload),
                "Stopped",
                "Stopped  /  No incomplete output was committed",
            )
        elif kind == "error":
            if self.__dict__.get("_closing", False):
                self._append_log(f"ERROR during application close: {payload}")
                return True
            failed_job = self.active_job
            if self._library_run_is_suppressed(failed_job):
                self._finish_run_ui(
                    "Removed from Library; the run was stopped.",
                    "Stopped",
                    "Stopped  /  Removed from Library",
                )
                return True
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
            if not self._launch_next_pending_job() and hasattr(
                self, "focus_transfer_var"
            ):
                self._set_focus_run_controls_visible(False)
                self._refresh_focus_run_deck()
            if failed_job is not None:
                self._focus_terminal_job(failed_job)
        else:
            return False
        return True
