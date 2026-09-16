from __future__ import annotations

import copy
import json
import os
import time
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any

from .archive_browser import archive_row_owner, media_source_identity
from .archive_observations import history_failure, history_operation, relink_dimensions
from .archive_observations import operation as archive_operation
from .archive_observations import usage as archive_usage
from .archive_paths import ArchivePath, RootMapping
from .archive_relink import (
    RelinkCancelled,
    commit_relink,
    preview_relink,
    record_fingerprint,
    recorded_artifact,
    verify_relink,
)
from .archive_work import ArchiveWorkOwner
from .failure_diagnostics import FailureDiagnostic, capture_failure
from .history import (
    HistoryError,
    history_archive_owner,
    load_history,
    stage_history_mutation,
)
from .platform_services import open_path as open_system_path
from .telemetry_features import time_bucket
from .ui_theme import FONT_UI_SMALL, THEME
from .ui_widgets import SleekScrollbar, bind_smooth_vertical_wheel


class ArchiveLibraryMixin:
    """Library view coordination; canonical app history/player owners remain authoritative."""

    _media_player_window: Any
    _media_player_source: Any

    def _archive_initialize(self: Any) -> None:
        self._archive_worker = ArchiveWorkOwner()
        self._archive_callback = None
        self._archive_work_timeout = None
        self._archive_work_cancel = None
        self._archive_work_deadline = 0.0
        self._archive_commit_active = False
        self._archive_overlay = None
        self._archive_hidden: list[Any] = []
        self._archive_context_path = None
        self._archive_context_indices = ()
        self._archive_poller = self.after(50, self._archive_poll)
        self.bind("<Destroy>", self._archive_destroyed, add="+")

    def _archive_usage(self: Any, feature: str, action: str, **dimensions: str) -> None:
        archive_usage(
            self.__dict__.get("product_telemetry"), feature, action, dimensions
        )

    def _archive_observe(
        self: Any,
        feature: str,
        action: str,
        operation: str | None,
        *,
        failure_detail: FailureDiagnostic | None = None,
        **dimensions: str,
    ) -> None:
        archive_operation(
            self.__dict__.get("product_telemetry"),
            feature,
            action,
            operation,
            dimensions,
            failure_detail=failure_detail,
        )

    def _archive_history_observe(
        self: Any,
        action: str,
        operation: str,
        boundary: str,
        *,
        error: HistoryError | None = None,
        item_count: int | None = None,
    ) -> None:
        history_operation(
            self.__dict__.get("product_telemetry"),
            action,
            operation,
            boundary,
            error=error,
            item_count=item_count,
        )

    def _archive_cancel_work(self: Any) -> None:
        cancelled, self._archive_work_cancel = self._archive_work_cancel, None
        self._archive_worker.cancel()
        self._archive_callback = self._archive_work_timeout = None
        self._archive_work_deadline = 0.0
        if cancelled is not None:
            cancelled()

    def _archive_submit(
        self: Any,
        kind: str,
        work: Any,
        done: Any,
        *,
        deadline: bool = True,
        on_timeout: Any = None,
        on_cancel: Any = None,
    ) -> bool:
        generation = self._archive_worker.submit(kind, work)
        if generation is None:
            self.status_var.set(
                "A storage check is still finishing. You can continue browsing."
            )
            return False
        self._archive_callback = done
        self._archive_work_timeout = on_timeout
        self._archive_work_cancel = on_cancel
        self._archive_work_deadline = time.monotonic() + 20.0 if deadline else 0.0
        return True

    def _archive_poll(self: Any) -> None:
        if self.__dict__.get("_closing"):
            if self._archive_commit_active:
                self._archive_worker.cancel(retire_result=False)
            else:
                self._archive_worker.close()
                return
        result = self._archive_worker.poll()
        if result is not None:
            callback, self._archive_callback = self._archive_callback, None
            self._archive_work_deadline = 0.0
            self._archive_work_timeout = self._archive_work_cancel = None
            self._event_write_diagnostic(
                "archive work "
                + json.dumps(
                    {
                        "phase": result.kind,
                        "elapsed_ms": result.elapsed_ms,
                        "outcome": "failed" if result.error else "completed",
                        "error_category": result.error,
                    }
                )
            )
            if callback is not None:
                callback(result)
        elif (
            self._archive_work_deadline
            and time.monotonic() >= self._archive_work_deadline
        ):
            if self._archive_commit_active:
                # A write might already be crossing its atomic replace boundary.
                # Request cancellation, but retain the actual durable result.
                self._archive_work_deadline = 0.0
                self._archive_request_commit_cancel(timed_out=True)
            else:
                timed_out, self._archive_work_timeout = self._archive_work_timeout, None
                self._archive_work_cancel = None
                self._archive_cancel_work()
                if timed_out is not None:
                    timed_out()
                self.status_var.set(
                    "Storage did not respond in time. History is unchanged; reconnect the location and retry."
                )
                self._archive_status.set(
                    "Storage check timed out. No saved locations were changed."
                )
        pending = self.__dict__.get("_archive_pending_playback")
        if pending is not None:
            if self._closing or time.monotonic() >= pending["deadline"]:
                self._archive_retire_pending_playback()
                if not self._closing:
                    self.status_var.set(
                        "The saved location did not respond. Reconnect storage and retry playback."
                    )
            elif not self._archive_worker.busy and not self._archive_commit_active:
                self._archive_pending_playback = None
                owner = pending["owner"]
                current = next(
                    (
                        record
                        for record in self.metadata_items
                        if archive_row_owner(record) == owner
                    ),
                    None,
                )
                if current is None:
                    self._record_playback_operation(pending["operation"], "cancelled")
                else:
                    self._archive_request_playback(current, accepted=pending)
        if (
            self.__dict__.get("_archive_pending_artwork")
            and not self._closing
            and not self._archive_worker.busy
            and not self._archive_commit_active
        ):
            self._archive_pending_artwork = False
            selection = self.video_tree.selection()
            if selection:
                index = int(selection[0])
                self._archive_selected_artwork(index, self.metadata_items[index])
        self._archive_poller = self.after(50, self._archive_poll)

    def _archive_retire_pending_playback(self: Any) -> None:
        pending = self.__dict__.pop("_archive_pending_playback", None)
        if pending is not None:
            self._record_playback_operation(pending["operation"], "cancelled")

    def _archive_destroyed(self: Any, event: Any) -> None:
        if event.widget is self:
            self.__dict__.pop("_archive_deferred_history", None)
            self._archive_cancel_work()
            self._archive_worker.close()
            if self._archive_poller:
                try:
                    self.after_cancel(self._archive_poller)
                except tk.TclError:
                    pass

    def _build_archive_location_panel(self: Any, parent: Any) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        canvas = tk.Canvas(
            parent, bg=THEME["surface"], bd=0, highlightthickness=0, width=1
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = SleekScrollbar(parent, command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        content = ttk.Frame(canvas, style="FocusShell.TFrame")
        window = canvas.create_window(0, 0, anchor="nw", window=content)
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window, width=max(1, event.width)),
            add="+",
        )
        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
            add="+",
        )
        bind_smooth_vertical_wheel(canvas, content)
        self._archive_location_canvas = canvas
        parent = content
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(4, minsize=100)
        ttk.Label(parent, text="SAVED LOCATION", style="FocusEyebrow.TLabel").grid(
            row=0, column=0, sticky="w", pady=(8, 6)
        )
        self._archive_path_text = tk.Text(
            parent,
            height=4,
            width=1,
            wrap="char",
            bg=THEME["surface"],
            fg=THEME["text"],
            font=FONT_UI_SMALL,
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=8,
        )
        self._archive_path_text.grid(row=1, column=0, sticky="ew")
        self._archive_path_text.configure(state="disabled")
        self._archive_status = tk.StringVar(
            self, "Select a saved item or folder. Availability has not been checked."
        )
        ttk.Label(
            parent,
            textvariable=self._archive_status,
            style="Muted.TLabel",
            wraplength=290,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", pady=(8, 10))
        ttk.Label(
            parent, text="PARENTS · Double-click to open", style="FocusEyebrow.TLabel"
        ).grid(row=3, column=0, sticky="w", pady=(0, 5))
        shell = ttk.Frame(parent, style="FocusShell.TFrame")
        shell.grid(row=4, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)
        self._archive_ancestors = tk.Listbox(
            shell,
            width=1,
            height=6,
            bg=THEME["bg"],
            fg=THEME["text"],
            selectbackground=THEME["accent_surface"],
            bd=0,
            highlightthickness=0,
            font=FONT_UI_SMALL,
            exportselection=False,
        )
        self._archive_ancestors.grid(row=0, column=0, sticky="nsew")
        vertical = SleekScrollbar(shell, command=self._archive_ancestors.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = SleekScrollbar(
            shell, command=self._archive_ancestors.xview, orient="horizontal"
        )
        horizontal.grid(row=1, column=0, sticky="ew")
        self._archive_ancestors.configure(
            yscrollcommand=vertical.set, xscrollcommand=horizontal.set
        )
        self._archive_ancestors.bind(
            "<Double-1>", lambda _event: self._archive_open_parent()
        )
        self._archive_ancestors.bind(
            "<Return>", lambda _event: self._archive_open_parent()
        )
        actions = ttk.Frame(parent, style="FocusShell.TFrame")
        actions.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        for row, column, label, command in (
            (
                0,
                0,
                "Open saved folder",
                lambda: self._archive_open_path(self._archive_context_path),
            ),
            (0, 1, "Open selected parent", self._archive_open_parent),
            (1, 0, "Copy full path", self._archive_copy_path),
            (1, 1, "Check availability", self._archive_check_location),
            (2, 0, "Relink selected file", self._archive_relink_selected),
            (2, 1, "Update folder location", self._archive_relink_context),
        ):
            ttk.Button(
                actions, text=label, command=command, style="FocusQuiet.TButton"
            ).grid(row=row, column=column, sticky="ew", padx=2, pady=3)

    def _archive_context(
        self: Any, path: ArchivePath | None, indices: tuple[int, ...]
    ) -> None:
        self._archive_context_path, self._archive_context_indices = path, indices
        self._archive_path_text.configure(state="normal")
        self._archive_path_text.delete("1.0", "end")
        self._archive_path_text.insert(
            "1.0", str(path) if path else "This item has no saved folder."
        )
        self._archive_path_text.configure(state="disabled")
        self._archive_parent_paths = path.ancestry if path else ()
        self._archive_ancestors.delete(0, "end")
        for ancestor in self._archive_parent_paths:
            self._archive_ancestors.insert("end", str(ancestor))
        self._archive_status.set(
            "Availability not checked. An offline drive does not remove this item from your archive."
        )
        if path:
            self._archive_ancestors.selection_set(len(self._archive_parent_paths) - 1)
            self._archive_ancestors.see("end")

    def _archive_folder_selected(
        self: Any, path: ArchivePath, indices: tuple[int, ...]
    ) -> None:
        self._archive_context(path, indices)
        self.focus_archive_inspector.select(self.focus_archive_location_tab)

    def _archive_copy_path(self: Any) -> None:
        if self._archive_context_path:
            self.clipboard_clear()
            self.clipboard_append(str(self._archive_context_path))
            self.status_var.set("Saved path copied.")
            self._archive_usage("archive", "location_copied")

    def _archive_open_parent(self: Any) -> None:
        selected = self._archive_ancestors.curselection()
        if selected:
            self._archive_open_path(self._archive_parent_paths[selected[0]])

    def _archive_open_path(self: Any, path: ArchivePath | None) -> None:
        if path is not None:
            self._archive_location_request(path, "open")

    def _archive_check_location(self: Any) -> None:
        if self._archive_context_path is not None:
            self._archive_location_request(self._archive_context_path, "check")

    def _archive_location_request(self: Any, path: ArchivePath, action: str) -> None:
        key = str(uuid.uuid4())
        feature = "archive_location_operation"
        dimensions = {"storage_kind": path.storage[0], "location_action": action}

        def work(cancelled: Any) -> str:
            if (path.style == "windows") != (os.name == "nt"):
                return "foreign_platform"
            native = Path(str(path))
            try:
                if not native.is_dir():
                    kind, root = path.storage
                    return (
                        "unavailable"
                        if kind != "local" and not Path(str(root)).is_dir()
                        else "missing"
                    )
                if cancelled.is_set():
                    return "cancelled"
                if action == "open":
                    open_system_path(native)
                    return "opened"
                return "available"
            except OSError:
                return "unavailable"

        def done(result: Any) -> None:
            outcome = result.value if not result.error else "unavailable"
            succeeded = outcome in {"opened", "available"}
            self._archive_observe(
                feature,
                "completed" if succeeded else "failed",
                key,
                **dimensions,
                archive_result=outcome,
                processing_bucket=time_bucket(result.elapsed_ms / 1000),
            )
            # A location result is never allowed to relabel a newly selected folder.
            browser = self.__dict__.get("video_tree")
            if browser is not None and hasattr(browser, "set_location_state"):
                browser.set_location_state(path, outcome)
            if self._archive_context_path != path:
                return
            messages = {
                "opened": "Folder opened.",
                "available": "Folder is available. Files are checked individually before playback or relinking.",
                "foreign_platform": "This path belongs to another platform. Choose its location on this computer.",
                "missing": "Folder was not found. If you moved it, update its saved location.",
                "unavailable": "Storage is offline or unavailable. Reconnect it; your history is retained.",
                "cancelled": "Storage check cancelled.",
            }
            text = messages.get(outcome, messages["unavailable"])
            self._archive_status.set(text)
            self.status_var.set(text)

        if self._archive_submit(
            "open_location" if action == "open" else "availability",
            work,
            done,
            on_timeout=lambda: self._archive_observe(
                feature, "timed_out", key, **dimensions
            ),
            on_cancel=lambda: self._archive_observe(
                feature, "cancelled", key, **dimensions
            ),
        ):
            self._archive_observe(feature, "requested", key, **dimensions)
            self._archive_status.set("Checking this exact saved folder…")

    def _archive_relink_selected(self: Any) -> None:
        selection = self.video_tree.selection()
        if not selection:
            self.status_var.set("Select a saved export to relink.")
            return
        index = int(selection[0])
        chosen = filedialog.askopenfilename(
            parent=self, title="Choose the moved media file"
        )
        if chosen:
            self._archive_begin_relink(None, (index,), exact=chosen)

    def _archive_relink_context(self: Any) -> None:
        if self._archive_context_path:
            self._archive_relink_folder(
                self._archive_context_path, self._archive_context_indices
            )

    def _archive_relink_folder(
        self: Any, path: ArchivePath, indices: tuple[int, ...]
    ) -> None:
        chosen = filedialog.askdirectory(
            parent=self, title="Choose this folder's new location", mustexist=True
        )
        if chosen:
            self._archive_begin_relink(path, indices, destination=chosen)

    def _archive_show_overlay(self: Any, parent: Any) -> Any:
        if self._archive_overlay is not None:
            self._archive_restore_browser()
        self._archive_hidden = [
            widget for widget in parent.grid_slaves() if widget.winfo_manager()
        ]
        for widget in self._archive_hidden:
            widget.grid_remove()
        panel = ttk.Frame(parent, style="FocusShell.TFrame")
        panel.grid(row=0, column=0, rowspan=3, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)
        self._archive_overlay = panel
        return panel

    def _archive_restore_browser(self: Any) -> None:
        overlay, self._archive_overlay = self._archive_overlay, None
        if overlay is not None:
            overlay.destroy()
        for widget in self._archive_hidden:
            try:
                widget.grid()
            except tk.TclError:
                pass
        self._archive_hidden = []
        self._apply_focus_layout(force=True)

    def _archive_cancel_relink(self: Any) -> None:
        if self._archive_commit_active:
            self._archive_request_commit_cancel()
            return
        self._archive_cancel_work()
        key = self.__dict__.pop("_archive_relink_operation", None)
        self._archive_observe("archive_relink_operation", "cancelled", key)
        self._archive_restore_browser()

    def _archive_request_commit_cancel(self: Any, *, timed_out: bool = False) -> None:
        self._archive_worker.cancel(retire_result=False)
        if not self.__dict__.get("_archive_commit_cancel_reason"):
            self._archive_commit_cancel_reason = "timeout" if timed_out else "cancel"
            self._archive_observe(
                "archive_relink_operation",
                "cancel_requested",
                self.__dict__.get("_archive_relink_operation"),
            )
        status = self.__dict__.get("_archive_commit_status")
        if status is not None:
            status.set(
                "Cancellation requested. Waiting for storage to confirm the outcome; "
                "other history changes will be saved after this operation settles."
            )

    def _archive_defer_history(
        self: Any, key: Any, callback: Any, *, mutation: dict[str, Any]
    ) -> None:
        # The durable delta must precede acknowledgement and callback deferral.
        operation = str(uuid.uuid4())
        ArchiveLibraryMixin._archive_history_observe(
            self, "started", operation, "defer"
        )
        try:
            stage_history_mutation(self.history_path, mutation)
        except HistoryError as exc:
            ArchiveLibraryMixin._archive_history_observe(
                self, "failed", operation, "defer", error=exc
            )
            raise
        self.__dict__.setdefault("_archive_deferred_history", {})[key] = callback
        ArchiveLibraryMixin._archive_history_observe(
            self, "deferred", operation, "defer"
        )

    def _archive_flush_history(self: Any) -> bool:
        callbacks = self.__dict__.pop("_archive_deferred_history", {})
        operation = str(uuid.uuid4())
        ArchiveLibraryMixin._archive_history_observe(
            self, "started", operation, "settlement"
        )
        try:
            # Recover the accepted deltas onto the actual committed ledger first.
            # Live callbacks may contain newer activity and must not be overwritten
            # by an earlier journal snapshot.
            self.download_history = load_history(
                self.history_path,
                on_recovered=lambda count: ArchiveLibraryMixin._archive_history_observe(
                    self, "recovered", operation, "settlement", item_count=count
                ),
            )
            for callback in callbacks.values():
                callback()
            self.download_history = load_history(self.history_path)
        except HistoryError as exc:
            self._history_recovery_blocked = True
            ArchiveLibraryMixin._archive_history_observe(
                self, "failed", operation, "settlement", error=exc
            )
            self.status_var.set(
                "History recovery needs attention. Pending updates have been retained for the next launch."
            )
            self._event_write_diagnostic("pending history recovery could not finish")
            return False
        ArchiveLibraryMixin._archive_history_observe(
            self, "completed", operation, "settlement"
        )
        return True

    def _archive_begin_relink(
        self: Any,
        source: ArchivePath | None,
        indices: tuple[int, ...],
        *,
        destination: str = "",
        exact: str = "",
    ) -> None:
        if self._archive_worker.busy:
            self.status_var.set(
                "Wait for the current storage check to finish before reviewing locations."
            )
            return
        history = copy.deepcopy(self.download_history)
        owners = {
            history_archive_owner(record): index for index, record in enumerate(history)
        }
        selected = tuple(
            dict.fromkeys(
                owners[archive_row_owner(self.metadata_items[index])]
                for index in indices
                if archive_row_owner(self.metadata_items[index]) in owners
            )
        )
        if not selected:
            self.status_var.set(
                "Only saved exports can be relinked. Runs and previews remain unchanged."
            )
            return
        mappings = (
            (RootMapping(source, ArchivePath.parse(destination)),)
            if source and destination
            else ()
        )
        proposal = preview_relink(
            history,
            mappings,
            selected=selected,
            exact_files={selected[0]: exact} if exact else {},
        )
        key = str(uuid.uuid4())
        self._archive_relink_operation = key
        self._archive_observe(
            "archive_relink_operation",
            "requested",
            key,
            relink_mode="file" if exact else "folder",
            **relink_dimensions(proposal),
        )
        panel = self._archive_show_overlay(self.focus_library_view)
        header = ttk.Frame(panel, style="FocusShell.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=16)
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, text="Review saved locations", style="FocusTitle.TLabel"
        ).grid(row=0, column=0, sticky="w")
        cancel = ttk.Button(
            header,
            text="Back to archive",
            command=self._archive_cancel_relink,
            style="FocusQuiet.TButton",
        )
        cancel.grid(row=0, column=1)
        status = tk.StringVar(panel, "Checking exact proposed files…")
        ttk.Label(
            panel,
            textvariable=status,
            style="Muted.TLabel",
            wraplength=820,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        document = tk.Text(
            panel,
            width=1,
            wrap="word",
            bg=THEME["surface"],
            fg=THEME["text"],
            font=FONT_UI_SMALL,
            bd=0,
            highlightthickness=0,
            padx=16,
            pady=12,
        )
        document.grid(row=2, column=0, sticky="nsew", padx=18)
        scrollbar = SleekScrollbar(panel, command=document.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        document.configure(yscrollcommand=scrollbar.set)
        actions = ttk.Frame(panel, style="FocusShell.TFrame")
        actions.grid(row=3, column=0, sticky="ew", padx=18, pady=16)
        ttk.Label(
            actions,
            text="This updates Library references only. No media or companion files are moved or changed.",
            style="Muted.TLabel",
            wraplength=650,
        ).pack(side="left")
        apply = ttk.Button(
            actions,
            text="Update verified locations",
            state="disabled",
            style="Accent.TButton",
        )
        apply.pack(side="right")

        def show(preview: Any) -> None:
            document.configure(state="normal")
            document.delete("1.0", "end")
            for entry in preview.entries:
                title = history[entry.index].get("title") or "Saved export"
                document.insert(
                    "end",
                    f"{entry.state.upper()} · {title}\nFrom: {entry.source or 'Exact file was not recorded'}\nTo: {entry.destination or 'Choose a destination'}\n\n",
                )
            document.configure(state="disabled")

        show(proposal)

        def verified(result: Any) -> None:
            if result.error or result.value is None:
                self._archive_observe(
                    "archive_relink_operation",
                    "failed",
                    key,
                    archive_result="unavailable",
                )
                status.set(
                    "Verification failed. No history was changed. Reconnect the location and retry."
                )
                return
            preview = result.value
            self._archive_observe(
                "archive_relink_operation",
                "verified",
                key,
                **relink_dimensions(preview),
            )
            self._event_write_diagnostic(
                "archive relink " + json.dumps(preview.diagnostic("verify"))
            )
            show(preview)
            ready = tuple(
                entry.index for entry in preview.entries if entry.state == "ready"
            )
            status.set(
                f"{len(ready)} exact files found; {len(preview.entries) - len(ready)} unresolved. Review every destination before applying. File presence does not prove identical content."
            )
            if ready:
                apply.configure(
                    state="normal",
                    text=f"Update {len(ready)} verified locations",
                    command=lambda: self._archive_apply_relink(
                        preview, history, ready, status, apply, cancel
                    ),
                )

        self._archive_submit(
            "relink_verify",
            lambda cancelled: verify_relink(proposal, history, cancelled=cancelled),
            verified,
            on_timeout=lambda: self._archive_observe(
                "archive_relink_operation", "timed_out", key
            ),
        )

    def _archive_apply_relink(
        self: Any,
        preview: Any,
        history: Any,
        accepted: Any,
        status: Any,
        button: Any,
        cancel: Any,
    ) -> None:
        key = self.__dict__.get("_archive_relink_operation")
        if (
            tuple(record_fingerprint(record) for record in self.download_history)
            != preview.snapshot
        ):
            self._archive_observe("archive_relink_operation", "stale", key)
            status.set(
                "Archive changed while you reviewed it. Return and verify the locations again."
            )
            button.configure(state="disabled")
            return
        selected_history_index = None
        browser = self.__dict__.get("video_tree")
        if browser is not None and browser.selection():
            selected_owner = archive_row_owner(
                self.metadata_items[int(browser.selection()[0])]
            )
            selected_history_index = next(
                (
                    index
                    for index, record in enumerate(history)
                    if history_archive_owner(record) == selected_owner
                ),
                None,
            )
        self._archive_commit_active = True
        self._archive_commit_cancel_reason = ""
        self._archive_commit_status = status
        self._archive_observe(
            "archive_relink_operation",
            "commit_requested",
            key,
            item_count=str(len(accepted)),
        )
        button.configure(state="disabled")
        cancel.configure(state="normal", text="Cancel pending update")
        status.set("Rechecking files and saving the verified locations…")

        def work(cancelled: Any) -> Any:
            try:
                updated = commit_relink(
                    preview,
                    history,
                    self.history_path,
                    accepted=accepted,
                    cancelled=cancelled,
                )
            except Exception as exc:
                if isinstance(exc, RelinkCancelled):
                    self._archive_observe(
                        "archive_relink_operation",
                        "timed_out"
                        if self.__dict__.get("_archive_commit_cancel_reason")
                        == "timeout"
                        else "cancelled",
                        key,
                    )
                else:
                    self._archive_observe(
                        "archive_relink_operation",
                        "failed",
                        key,
                        archive_result="changed"
                        if isinstance(exc, ValueError)
                        else "write_failed",
                        failure_detail=history_failure(exc)
                        if isinstance(exc, HistoryError)
                        else capture_failure(exc, stage="commit", inspect_text=False),
                        **(
                            {
                                "history_document": exc.document,
                                "history_phase": exc.phase,
                            }
                            if isinstance(exc, HistoryError)
                            else {}
                        ),
                    )
                raise
            # Observe the real save boundary, even if the UI closes before polling.
            self._archive_observe(
                "archive_relink_operation",
                "committed",
                key,
                committed_count=str(len(accepted)),
                **relink_dimensions(preview),
            )
            return updated

        def done(result: Any) -> None:
            self._archive_commit_active = False
            self._archive_commit_status = None
            cancel.configure(state="normal", text="Back to archive")
            if result.error or result.value is None:
                if not self._archive_flush_history():
                    status.set(
                        "No relink was saved. Pending history recovery needs attention before further edits."
                    )
                    return
                status.set(
                    "No relink was saved. The operation was cancelled, the locations changed, "
                    "or history could not be written. Return to review the locations again."
                )
                return
            self._archive_relink_operation = None
            self.download_history = result.value
            if not self._archive_flush_history():
                status.set(
                    "Saved locations were updated. Pending history recovery needs attention before further edits."
                )
                return
            self._reconcile_library_projection()
            if not self.__dict__.get("_closing"):
                if selected_history_index is not None:
                    # The first relink replaces a path owner with a stable archive
                    # owner. Follow that exact committed row even if deferred
                    # writers inserted another row before it.
                    updated_owner = history_archive_owner(
                        result.value[selected_history_index]
                    )
                    selected_index = next(
                        (
                            index
                            for index, record in enumerate(self.metadata_items)
                            if archive_row_owner(record) == updated_owner
                        ),
                        None,
                    )
                    if selected_index is not None:
                        self.video_tree.see(str(selected_index))
                        self.video_tree.selection_set(str(selected_index))
                        self._display_selected_metadata(selected_index)
                self._archive_restore_browser()
                self.status_var.set(
                    f"Updated {len(accepted)} saved locations. Unresolved items and all media files were left unchanged."
                )

        if not self._archive_submit("relink_apply", work, done):
            self._archive_commit_active = False
            self._archive_commit_status = None
            cancel.configure(state="normal", text="Back to archive")

    def _archive_show_inspector(self: Any) -> None:
        self._archive_usage("archive", "inspector_opened")
        self._archive_inspector_expanded = not self.__dict__.get(
            "_archive_inspector_expanded", False
        )
        self._apply_focus_layout(force=True)

    def _apply_archive_layout(self: Any, width: int, _height: int) -> None:
        expanded = self.__dict__.get("_archive_inspector_expanded", False)
        compact = width < 1260
        self.focus_library_category_filter.set_compact(compact)
        self.focus_library_search_field.set_compact(compact)
        self.focus_library_details_button.configure(
            text="Back to browse" if compact and expanded else "Item details"
        )
        if not self.focus_library_details_button.winfo_manager():
            self.focus_library_details_button.pack(
                side="left", padx=(6, 0), before=self.focus_library_menu_button
            )
        if compact:
            self.focus_metadata_content.columnconfigure(1, weight=0, minsize=0)
            if expanded:
                self.focus_queue_panel.grid_remove()
                self.focus_archive_inspector.grid(
                    row=0, column=0, columnspan=2, sticky="nsew"
                )
            else:
                self.focus_archive_inspector.grid_remove()
                self.focus_queue_panel.grid(
                    row=0, column=0, columnspan=2, sticky="nsew", padx=0
                )
        else:
            self.focus_metadata_content.columnconfigure(1, weight=0, minsize=350)
            self.focus_queue_panel.grid(
                row=0, column=0, columnspan=1, sticky="nsew", padx=(0, 18)
            )
            self.focus_archive_inspector.grid(
                row=0, column=1, columnspan=1, sticky="nsew"
            )

    def _archive_activate_item(self: Any, index: int) -> None:
        info = self.metadata_items[index]
        if info.get("vodforge_output_dir"):
            self._play_selected_library_item(info)
        elif info.get("vodforge_preview_complete"):
            self._start_preview_download(info)
        elif (job := self._terminal_job_for_metadata(info)) is not None:
            self._retry_terminal_job(job)

    def _archive_selected_artwork(self: Any, index: int, info: Any) -> None:
        from .app import best_thumbnail

        thumbnail = best_thumbnail(info)
        self.last_thumbnail_url = str((thumbnail or {}).get("url") or "") or None
        owner = archive_row_owner(info)
        key = (owner, record_fingerprint(info))
        if (
            self.__dict__.get("_archive_artwork_owner") == key
            and time.monotonic() - self.__dict__.get("_archive_artwork_checked_at", 0)
            < 30
        ):
            return
        self._archive_artwork_owner = key
        self._archive_artwork_checked_at = time.monotonic()
        self._invalidate_thumbnail_request("library")
        if self.__dict__.get("_focus_brand_source_image") is not None:
            self._render_focus_thumbnail_surfaces(
                self._focus_brand_source_image, placeholder=True, target="library"
            )
        if self._archive_worker.busy:
            # No optional artwork may queue behind or compete with a relink.
            self._archive_artwork_owner = ""
            self._archive_pending_artwork = True
            return
        self._archive_pending_artwork = False
        snapshot = dict(info)

        def work(cancelled: Any) -> Any:
            from PIL import Image

            path = self._library_thumbnail_path(snapshot)
            if path is None or cancelled.is_set():
                return None
            with Image.open(path) as image:
                image.thumbnail((480, 270))
                return image.convert("RGB").copy(), path

        def done(result: Any) -> None:
            selection = self.video_tree.selection()
            if (
                not selection
                or (
                    archive_row_owner(self.metadata_items[int(selection[0])]),
                    record_fingerprint(self.metadata_items[int(selection[0])]),
                )
                != key
            ):
                return
            if result.value is not None:
                image, path = result.value
                self._render_focus_thumbnail_surfaces(
                    image, placeholder=False, source_path=path, target="library"
                )
            elif self.last_thumbnail_url:
                self._load_thumbnail_preview(
                    self.last_thumbnail_url, target="library", cache_info=snapshot
                )

        self._archive_submit("selected_artwork", work, done)

    def _archive_request_playback(
        self: Any, info: Any, *, accepted: Any = None
    ) -> None:
        import uuid

        from .media_player import resolve_library_media_path

        if accepted is None:
            self._archive_retire_pending_playback()
            origin = self.__dict__.get("_focus_selected_view", "library")
            origin = origin if origin in {"library", "watch"} else "library"
            operation = str(uuid.uuid4())
            self.__dict__.setdefault("_archive_playback_origins", {})[operation] = (
                origin
            )
            self._record_playback_operation(operation, "requested")
            accepted = {
                "operation": operation,
                "origin": origin,
                "owner": archive_row_owner(info),
                "deadline": time.monotonic() + 20.0,
            }
        existing = self.__dict__.get("_media_player_window")
        if existing is not None and not existing.closed:
            try:
                recorded = recorded_artifact(info)
                current = ArchivePath.parse(str(self._media_player_source))
            except (ValueError, TypeError):
                recorded = None
                current = None
            if (
                recorded is not None
                and current is not None
                and recorded.key == current.key
            ):
                existing.focus_existing()
                self._record_playback_operation(accepted["operation"], "focused")
                return
        if self._archive_worker.busy or self._archive_commit_active:
            # One latest accepted intent survives optional artwork/storage readiness.
            self._archive_pending_playback = accepted
            self.status_var.set(
                "Opening saved media when the current storage check finishes…"
            )
            return
        existing = self.__dict__.get("_media_player_window")
        if existing is not None:
            existing.close()
        self._media_player_launch_generation += 1
        generation = self._media_player_launch_generation
        self._archive_player_origin = accepted["origin"]
        operation = accepted["operation"]
        self._archive_opening_operation = operation
        snapshot = dict(info)
        panel = self._archive_show_overlay(
            self._focus_views[self._archive_player_origin]
        )
        self._archive_playback_host = panel
        loading = ttk.Label(
            panel, text="Opening saved media…", style="FocusTitle.TLabel"
        )
        loading.grid(row=1, column=0, pady=24)
        ttk.Button(
            panel,
            text="Back to browse",
            command=self._archive_cancel_playback,
            style="FocusQuiet.TButton",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=12)

        def work(cancelled: Any) -> Any:
            path = resolve_library_media_path(snapshot)
            if cancelled.is_set():
                return None
            if path is None:
                return (
                    None,
                    self.library_media_recovery.plan(
                        snapshot, completed_jobs=tuple(self._terminal_jobs)
                    ),
                    None,
                )
            image = None
            from PIL import Image

            thumbnail = self._library_thumbnail_path(snapshot)
            if thumbnail is not None and not cancelled.is_set():
                try:
                    with Image.open(thumbnail) as source:
                        source.thumbnail((1280, 720))
                        image = source.convert("RGB").copy()
                except (OSError, ValueError):
                    pass
            return path, None, image

        def done(result: Any) -> None:
            if generation != self._media_player_launch_generation or self._closing:
                return
            if result.error or result.value is None:
                self._archive_playback_error(
                    "The saved location could not be read. Reconnect the drive or update its location."
                )
                self._record_playback_operation(operation, "failed")
                return
            path, plan, image = result.value
            if path is None:
                self._archive_missing_media(snapshot, plan)
                self._record_playback_operation(operation, "failed")
                return
            from .platform_services import find_runtime_executable

            ffmpeg = find_runtime_executable("ffmpeg")
            if not ffmpeg or self.playback_engine is None:
                self._record_playback_operation(operation, "failed")
                self._archive_playback_error(
                    "The bundled playback engine is unavailable. Reinstall VODForge or open the saved location."
                )
                return
            self._archive_poster_image = image
            self.playback_engine.start()
            self._open_library_player_when_ready(
                snapshot,
                path,
                ffmpeg=ffmpeg,
                launch_generation=generation,
                deadline=time.monotonic() + 10.0,
                operation=operation,
            )

        if not self._archive_submit(
            "playback_resolve",
            work,
            done,
            on_timeout=lambda: (
                self._record_playback_operation(operation, "failed"),
                self._archive_playback_error(
                    "The saved location did not respond. Reconnect storage and try again."
                ),
            ),
            on_cancel=lambda: self._record_playback_operation(operation, "cancelled"),
        ):
            self._archive_restore_browser()

    def _archive_cancel_playback(self: Any) -> None:
        self._archive_retire_pending_playback()
        self._media_player_launch_generation += 1
        self._archive_cancel_work()
        existing = self.__dict__.get("_media_player_window")
        if existing is not None:
            existing.close()
        else:
            self._archive_restore_browser()

    def _archive_player_closed(self: Any) -> None:
        self._media_player_launch_generation += 1
        self._media_player_window = None
        self._media_player_source = None
        self._archive_poster_image = None
        if not self.__dict__.get("_closing"):
            self._archive_restore_browser()

    def _archive_playback_error(self: Any, message: str) -> None:
        panel = self._archive_playback_host
        for child in panel.winfo_children():
            child.destroy()
        ttk.Button(
            panel,
            text="Back to browse",
            command=self._archive_cancel_playback,
            style="FocusQuiet.TButton",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=12)
        ttk.Label(panel, text="Media needs attention", style="FocusTitle.TLabel").grid(
            row=1, column=0, sticky="w", padx=18, pady=10
        )
        ttk.Label(
            panel, text=message, style="Muted.TLabel", wraplength=780, justify="left"
        ).grid(row=2, column=0, sticky="nw", padx=18, pady=10)

    def _archive_missing_media(self: Any, info: Any, plan: Any) -> None:
        from .library_media_recovery_ui import library_media_recovery_prompt

        prompt = library_media_recovery_prompt(plan)
        self._record_feature("missing_media", "offered")
        self._archive_playback_error(prompt.message)
        panel = self._archive_playback_host
        actions = ttk.Frame(panel, style="FocusShell.TFrame")
        actions.grid(row=3, column=0, sticky="w", padx=18, pady=18)

        def locate() -> None:
            owner = archive_row_owner(info)
            index = next(
                (
                    index
                    for index, record in enumerate(self.metadata_items)
                    if archive_row_owner(record) == owner
                ),
                None,
            )
            if index is None:
                return
            self._archive_cancel_playback()
            self._select_focus_view("library")
            self.library_output_type_var.set("All")
            self.video_tree.selection_set(str(index))
            self._archive_relink_selected()

        ttk.Button(
            actions, text="Locate moved file", command=locate, style="Accent.TButton"
        ).pack(side="left", padx=(0, 10))
        if prompt.primary_action == "redownload":
            ttk.Button(
                actions,
                text=prompt.primary_label,
                command=lambda: (
                    self._archive_cancel_playback(),
                    self._accept_library_redownload(plan),
                ),
                style="FocusQuiet.TButton",
            ).pack(side="left")
        elif prompt.primary_action == "open_forge":
            ttk.Button(
                actions,
                text=prompt.primary_label,
                command=lambda: (
                    self._archive_cancel_playback(),
                    self._open_missing_media_in_forge(info, plan),
                ),
                style="FocusQuiet.TButton",
            ).pack(side="left")

    def _archive_watch_details(self: Any, index: int) -> None:
        self._archive_usage("watch", "details")
        self._select_record_in_library({"metadata_index": index})
        self._select_focus_view("library")
        self._archive_inspector_expanded = True
        self._apply_focus_layout(force=True)

    def _archive_update_versions(self: Any, index: int) -> None:
        record = self.metadata_items[index]
        identity = (
            *media_source_identity(record),
            str(record.get("playlist_id") or ""),
        )
        indices = tuple(
            candidate
            for candidate in self.video_tree.model.visible
            if (
                *media_source_identity(self.metadata_items[candidate]),
                str(self.metadata_items[candidate].get("playlist_id") or ""),
            )
            == identity
            and self.metadata_items[candidate].get("vodforge_output_dir")
        )
        self._archive_variant_indices = indices or (index,)
        from .run_identity import metadata_output_profile

        values = tuple(
            f"{position + 1}. {metadata_output_profile(self.metadata_items[candidate])}"
            for position, candidate in enumerate(self._archive_variant_indices)
        )
        self._archive_variant_choice.configure(values=values)
        if index in self._archive_variant_indices:
            self._archive_variant_choice.set(
                values[self._archive_variant_indices.index(index)]
            )

    def _archive_choose_version(self: Any, _event: Any = None) -> None:
        values = tuple(self._archive_variant_choice.cget("values"))
        selected = self._archive_variant_choice.get()
        position = values.index(selected) if selected in values else -1
        indices = self.__dict__.get("_archive_variant_indices", ())
        if 0 <= position < len(indices):
            self._archive_usage("archive", "version_selected")
            index = indices[position]
            self.video_tree.model.reveal(index)
            self.video_tree.selection_set(str(index))
            self._display_selected_metadata(index)
