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

from .archive_browser import (
    archive_row_owner,
    media_source_identity,
    resolve_archive_subject,
)
from .archive_observations import (
    bind_operation,
    history_failure,
    history_operation,
    relink_dimensions,
)
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
from .product_telemetry import BoundProductOperation
from .telemetry_features import time_bucket
from .ui_button_contract import ProductButton
from .ui_chrome import prototype_treeview_style
from .ui_context_menu import ContextMenu
from .ui_layout import window_logical_metrics
from .ui_theme import FONT_UI_FAMILY, FONT_UI_SMALL, THEME
from .ui_widgets import (
    KeyboardScope,
    SleekScrollbar,
    ToolTip,
    bind_smooth_vertical_wheel,
)


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
        self._archive_relink_panel = None
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
        operation: str | BoundProductOperation | None,
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
                self._archive_retire_pending_playback(failed=not self._closing)
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
                    queue = self.__dict__.get("watch_queue")
                    if queue is not None and queue.owns(pending.get("queue_token")):
                        queue.cancel(
                            "failed",
                            failure_boundary="metadata",
                            failure_reason="source_removed",
                        )
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

    def _archive_retire_pending_playback(self: Any, *, failed: bool = False) -> None:
        pending = self.__dict__.pop("_archive_pending_playback", None)
        if pending is not None:
            self._record_playback_operation(pending["operation"], "cancelled")
            queue = self.__dict__.get("watch_queue")
            if queue is not None and queue.owns(pending.get("queue_token")):
                queue.cancel(
                    "failed" if failed else "cancelled",
                    failure_boundary="readiness",
                    failure_reason="storage_wait_expired",
                )

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
        canvas = tk.Canvas(parent, bg=THEME["bg"], bd=0, highlightthickness=0, width=1)
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
        ttk.Label(parent, text="Saved folder", style="FocusActiveTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(8, 6)
        )
        self._archive_path_text = tk.Text(
            parent,
            height=3,
            width=1,
            wrap="word",
            bg=THEME["bg"],
            fg=THEME["text"],
            font=FONT_UI_SMALL,
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=4,
        )
        self._archive_path_text.grid(row=1, column=0, sticky="ew")
        self._archive_path_text.configure(state="disabled")
        primary_actions = ttk.Frame(parent, style="FocusShell.TFrame")
        primary_actions.grid(row=2, column=0, sticky="w", pady=(12, 4))
        ProductButton(
            primary_actions,
            text="Open saved folder",
            command=lambda: self._archive_open_path(self._archive_context_path),
            style="Media.FocusQuiet.TButton",
        ).pack(side="left", padx=(0, 8))
        ProductButton(
            primary_actions,
            text="Copy full path",
            command=self._archive_copy_path,
            style="Media.FocusNav.TButton",
        ).pack(side="left")
        self._archive_status = tk.StringVar(
            self, "Select a saved item or folder. Availability has not been checked."
        )
        ttk.Label(
            parent,
            textvariable=self._archive_status,
            style="Muted.TLabel",
            wraplength=290,
            justify="left",
        ).grid(row=3, column=0, sticky="ew", pady=(8, 10))
        ttk.Label(parent, text="Folder path", style="FocusActiveTitle.TLabel").grid(
            row=4, column=0, sticky="w", pady=(16, 8)
        )
        shell = ttk.Frame(parent, style="FocusShell.TFrame")
        shell.grid(row=5, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1, minsize=80)
        self._archive_ancestors = ttk.Treeview(
            shell,
            show="tree",
            selectmode="browse",
            height=4,
            style=prototype_treeview_style(shell, "Archive.Folders.Treeview"),
            takefocus=True,
        )
        metrics = window_logical_metrics(shell)
        self._archive_ancestors.column(
            "#0", width=metrics.px(240), minwidth=metrics.px(120), stretch=True
        )
        self._archive_folder_icon = self._load_focus_icon(
            "folder", metrics.px(16), THEME["muted"]
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
        ToolTip(self._archive_ancestors, self._archive_parent_tooltip)
        ttk.Label(
            parent, text="Double-click a folder to open it.", style="Muted.TLabel"
        ).grid(row=6, column=0, sticky="w", pady=(8, 0))
        self._archive_location_options = ProductButton(
            parent,
            text="Location options  ▾",
            command=self._archive_location_menu,
            style="Media.FocusNav.TButton",
        )
        self._archive_location_options.grid(row=7, column=0, sticky="w", pady=(16, 8))

    def _archive_parent_tooltip(self: Any) -> str:
        paths = self.__dict__.get("_archive_parent_paths", ())
        if not paths:
            return ""
        row = self._archive_ancestors.identify_row(
            self._archive_ancestors.winfo_pointery()
            - self._archive_ancestors.winfo_rooty()
        )
        return str(paths[int(row)]) if row and 0 <= int(row) < len(paths) else ""

    def _archive_location_menu(self: Any) -> None:
        previous = self.__dict__.get("_archive_location_popup")
        if previous is not None:
            previous.destroy()
        menu = ContextMenu(self, tearoff=False)
        self._archive_location_popup = menu
        menu.add_command(
            label="Open selected parent", command=self._archive_open_parent
        )
        menu.add_command(
            label="Check availability", command=self._archive_check_location
        )
        menu.add_separator()
        menu.add_command(label="Find this file…", command=self._archive_relink_selected)
        menu.add_command(
            label="Find this folder…", command=self._archive_relink_context
        )
        anchor = self._archive_location_options
        try:
            menu.tk_popup(
                anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height()
            )
        finally:
            # Retain one menu for platforms with nonblocking popup posting.
            menu.grab_release()

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
        self._archive_ancestors.delete(*self._archive_ancestors.get_children())
        for depth, ancestor in enumerate(self._archive_parent_paths):
            self._archive_ancestors.insert(
                "",
                "end",
                iid=str(depth),
                text=("  " * min(depth, 4)) + "  " + (ancestor.name or str(ancestor)),
                image=self._archive_folder_icon or "",
            )
        self._archive_status.set("Availability not checked.")
        if path:
            last = str(len(self._archive_parent_paths) - 1)
            self._archive_ancestors.selection_set(last)
            self._archive_ancestors.see(last)

    def _archive_folder_selected(
        self: Any, path: ArchivePath, indices: tuple[int, ...]
    ) -> None:
        self._clear_library_selection()
        self._archive_folder_identity = True
        self.selected_title_var.set(path.name or str(path))
        self.selected_meta_var.set(
            f"{len(indices)} saved item" + ("s" if len(indices) != 1 else "")
        )
        self.focus_thumbnail_wrap.grid_remove()
        self.focus_library_play_button.pack_forget()
        self.focus_library_menu_button.pack_forget()
        self._queue_focus_selected_overview_layout()
        self._archive_context(path, indices)
        for tab in self.focus_archive_inspector.tabs():
            self.focus_archive_inspector.tab(
                tab,
                state="normal"
                if str(tab) == str(self.focus_archive_location_tab)
                else "hidden",
            )
        self.focus_archive_inspector.select(self.focus_archive_location_tab)

    def _archive_copy_path(self: Any) -> None:
        if self._archive_context_path:
            self.clipboard_clear()
            self.clipboard_append(str(self._archive_context_path))
            self.status_var.set("Saved path copied.")
            self._archive_usage("archive", "location_copied")

    def _archive_open_parent(self: Any) -> None:
        selected = self._archive_ancestors.selection()
        if selected:
            self._archive_open_path(self._archive_parent_paths[int(selected[0])])

    def _archive_open_path(self: Any, path: ArchivePath | None) -> None:
        if path is not None:
            self._archive_location_request(path, "open")

    def _archive_check_location(self: Any) -> None:
        if self._archive_context_path is not None:
            self._archive_location_request(self._archive_context_path, "check")

    def _archive_location_request(self: Any, path: ArchivePath, action: str) -> None:
        feature = "archive_location_operation"
        key = bind_operation(
            self.__dict__.get("product_telemetry"),
            feature,
            operation_key=str(uuid.uuid4()),
        )
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
        if not 0 <= index < len(self.metadata_items):
            return
        captured = self.metadata_items[index]
        chosen = filedialog.askopenfilename(
            parent=self, title="Choose the moved media file"
        )
        # The picker runs a nested loop: history may reorder while it is open.
        subject = resolve_archive_subject(self.metadata_items, captured)
        if chosen and subject is not None:
            self._archive_begin_relink(None, (subject[0],), exact=chosen)

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

    def _archive_retire_restoration(self: Any) -> None:
        pending = self.__dict__.pop("_archive_restore_reveal", None)
        if pending is not None:
            pending.cancel()

    def _archive_show_overlay(self: Any, parent: Any) -> Any:
        self._archive_retire_restoration()
        if self._archive_overlay is not None:
            self._archive_restore_browser()
            self._archive_retire_restoration()
        self._archive_hidden = [
            widget for widget in parent.grid_slaves() if widget.winfo_manager()
        ]
        panel: Any = ttk.Frame(parent, style="FocusShell.TFrame")
        panel.grid(
            row=0,
            column=0,
            rowspan=3,
            columnspan=max(1, parent.grid_size()[0]),
            sticky="nsew",
        )
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)
        self._archive_overlay = panel
        from .ui_transition import WidgetReveal

        panel._archive_reveal = WidgetReveal(
            panel,
            self._archive_hidden,
            current=lambda: self._archive_overlay is panel and not self._closing,
            escape=lambda: (
                self._archive_cancel_relink()
                if self.__dict__.get("_archive_relink_panel") is panel
                else self._archive_cancel_playback()
            ),
        )
        return panel

    def _archive_restore_browser(self: Any) -> None:
        self._archive_retire_restoration()
        overlay, self._archive_overlay = self._archive_overlay, None
        if self.__dict__.get("_archive_relink_panel") is overlay:
            self._archive_relink_panel = None
        if overlay is not None:
            reveal = getattr(overlay, "_archive_reveal", None)
            if reveal is not None:
                reveal.cancel()
        if self.__dict__.get("_archive_playback_host") is overlay:
            self._archive_playback_host = None
            self._archive_poster_image = None
        hidden, self._archive_hidden = self._archive_hidden, []
        for widget in hidden:
            try:
                widget.grid()
            except tk.TclError:
                pass
        # Responsive layout is supplied by the composed application host.
        host: Any = self
        host._apply_focus_layout(force=True)
        incoming = [w for w in hidden if w.winfo_exists() and w.winfo_manager()]
        if (
            overlay is not None
            and overlay.winfo_exists()
            and overlay.winfo_ismapped()
            and incoming
            and not self._closing
        ):
            from .ui_transition import WidgetReveal

            origin = self._focus_selected_view

            def finished() -> None:
                if self.__dict__.get("_archive_restore_reveal") is restoration:
                    self.__dict__.pop("_archive_restore_reveal", None)
                if overlay.winfo_exists():
                    overlay.destroy()

            restoration = WidgetReveal(
                incoming[0],
                [overlay],
                incoming=incoming,
                current=lambda: (
                    self.__dict__.get("_archive_restore_reveal") is restoration
                    and self._archive_overlay is None
                    and self._focus_selected_view == origin
                    and not self._closing
                ),
                escape=lambda: None,
                finished=finished,
            )
            self._archive_restore_reveal = restoration
            restoration.start()
        elif overlay is not None and overlay.winfo_exists():
            overlay.destroy()

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
                "Cancellation requested. Waiting to confirm whether your changes were saved."
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
        key = bind_operation(
            self.__dict__.get("product_telemetry"),
            "archive_relink_operation",
            operation_key=str(uuid.uuid4()),
        )
        self._archive_relink_operation = key
        self._archive_observe(
            "archive_relink_operation",
            "requested",
            key,
            relink_mode="file" if exact else "folder",
            **relink_dimensions(proposal),
        )
        panel = self._archive_show_overlay(self.focus_library_view)
        self._archive_relink_panel = panel
        panel._archive_relink_keys = KeyboardScope(
            panel, {"<Escape>": self._archive_cancel_relink}
        )
        header = ttk.Frame(panel, style="FocusShell.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=16)
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, text="Review saved locations", style="FocusTitle.TLabel"
        ).grid(row=0, column=0, sticky="w")
        cancel = ProductButton(
            header,
            text="Back to Library",
            command=self._archive_cancel_relink,
            style="Media.FocusQuiet.TButton",
        )
        cancel.grid(row=0, column=1)
        status = tk.StringVar(panel, "Checking selected files…")
        panel._archive_relink_status = (
            status  # Keep the status alive after a refused review.
        )
        ttk.Label(
            panel,
            textvariable=status,
            style="Muted.TLabel",
            wraplength=820,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        review_surface = ttk.Frame(
            panel, style="Material.TFrame", padding=(18, 12), height=120
        )
        review_surface.grid(row=2, column=0, sticky="new", padx=18)
        review_surface.grid_propagate(False)
        review_surface.columnconfigure(0, weight=1)
        review_surface.rowconfigure(0, weight=1)
        panel._archive_relink_review = review_surface
        document = tk.Text(
            review_surface,
            width=1,
            wrap="word",
            bg=THEME["panel"],
            fg=THEME["text"],
            font=FONT_UI_SMALL,
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=4,
        )
        document.grid(row=0, column=0, sticky="nsew")
        document.tag_configure(
            "review-title", font=(FONT_UI_FAMILY, 15, "bold"), spacing3=6
        )
        document.tag_configure("review-state", foreground=THEME["muted"], spacing3=12)
        document.tag_configure("review-ready", foreground=THEME["accent"])
        document.tag_configure(
            "review-attention", foreground=THEME.get("warning", THEME["text"])
        )
        document.tag_configure(
            "review-label", foreground=THEME["muted"], spacing1=8, spacing3=3
        )
        document.tag_configure("review-value", spacing3=8)
        document.tag_configure("review-note", foreground=THEME["muted"], spacing3=10)
        document.tag_configure("review-gap", spacing1=12, spacing3=12)
        bind_smooth_vertical_wheel(document, mode="pixels")
        scrollbar = SleekScrollbar(review_surface, command=document.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(10, 0))
        document.configure(yscrollcommand=scrollbar.set)

        def fit_review(_event: Any = None) -> None:
            if panel.winfo_height() <= 1 or document.winfo_width() <= 1:
                return
            # One native document keeps large reviews bounded. Only its material
            # grows with content; a single item does not become a full-page slab.
            available = max(100, panel.grid_bbox(0, 2, 1, 2)[3])
            # Every review line uses the base font or a larger title, without
            # elision. This prefix is enough to fill the available height, even
            # before wrapping; measuring the rest cannot change the clamp.
            line_height = max(
                1,
                int(
                    document.tk.call(
                        "font", "metrics", document.cget("font"), "-linespace"
                    )
                ),
            )
            end = f"{available // line_height + 2}.0"
            # Refresh only those line metrics, never the application event loop.
            measured = document.count("1.0", end, "update", "ypixels")
            pixels = int(
                measured if isinstance(measured, int) else (measured or (0,))[0]
            )
            height = min(available, max(100, pixels + 34))
            if int(review_surface.cget("height")) != height:
                review_surface.configure(height=height)

        panel.bind("<Configure>", fit_review, add="+")
        document.bind("<Configure>", fit_review, add="+")
        actions = ttk.Frame(panel, style="FocusShell.TFrame")
        actions.grid(row=3, column=0, sticky="ew", padx=18, pady=16)
        ttk.Label(
            actions,
            text="Updates saved locations in your Library. Your files stay where they are.",
            style="Muted.TLabel",
            wraplength=650,
        ).pack(side="left")
        apply = ProductButton(
            actions,
            text="Update locations",
            state="disabled",
            style="Accent.TButton",
        )
        apply.pack(side="right")

        relink_labels = {
            "pending": "Checking file",
            "ready": "File found",
            "unchanged": "Already saved here",
            "outside_mapping": "Choose a location for this file",
            "ambiguous_mapping": "More than one location matches",
            "invalid_destination": "Choose a valid location",
            "invalid_record": "Saved details need attention",
            "choose_file": "Choose the moved file",
            "collision": "Another saved item uses this file",
            "missing": "File not found or empty",
            "unavailable": "Location unavailable",
            "foreign_platform": "Choose a location on this computer",
            "identity_mismatch": "File does not match the saved format or details",
            "cancelled": "Check cancelled",
            "timed_out": "File check took too long",
            "stale": "Library changed; review this location again",
        }

        def show(preview: Any, *, pending_state: str | None = None) -> None:
            document.configure(state="normal")
            document.delete("1.0", "end")
            segments: list[Any] = []

            def append(text: str, tags: str | tuple[str, ...]) -> None:
                segments.extend((text, tags))

            for position, entry in enumerate(preview.entries):
                if position:
                    append("\n", "review-gap")
                record = history[entry.index]
                title = record.get("title") or "Saved export"
                append(f"{title}\n", "review-title")
                state = (
                    pending_state
                    if entry.state == "pending" and pending_state
                    else entry.state
                )
                state_tag = (
                    "review-ready"
                    if state == "ready"
                    else "review-state"
                    if state in {"pending", "unchanged"}
                    else "review-attention"
                )
                append(
                    f"{relink_labels[state]}\n",
                    ("review-state", state_tag),
                )
                recorded_format = str(record.get("vodforge_output_type") or "").strip()
                recorded_suffix = Path(entry.source.name).suffix if entry.source else ""
                if (
                    recorded_suffix
                    and recorded_suffix[1:].casefold() != recorded_format.casefold()
                ):
                    recorded_format = " · ".join(
                        value
                        for value in (recorded_format, recorded_suffix[1:].upper())
                        if value
                    )
                selected_format = (
                    Path(entry.destination.name).suffix[1:].upper()
                    if entry.destination
                    else ""
                )
                for label, value in (
                    ("Saved format", recorded_format or "Not recorded"),
                    ("Selected format", selected_format or "Not known"),
                    (
                        "Previous file" if entry.source else "Previous folder",
                        str(entry.source)
                        if entry.source
                        else str(record.get("vodforge_output_dir") or "Not recorded"),
                    ),
                    (
                        "Selected file",
                        str(entry.destination)
                        if entry.destination
                        else "Choose a destination",
                    ),
                ):
                    append(
                        label + (":   " if label.endswith("format") else "\n"),
                        "review-label",
                    )
                    append(value + "\n", "review-value")
                if entry.state == "identity_mismatch":
                    append(
                        "The file format or its accompanying metadata does not match this saved item.\n",
                        "review-note",
                    )
            if segments:
                # One tagged native insertion keeps large reviews from spending
                # their UI budget on thousands of Python/Tcl crossings. Tk owns
                # Unicode indices and tag ranges; no Python character offsets.
                document.insert("end", *segments)
            document.configure(state="disabled")
            fit_review()

        show(proposal)

        def verification_failed() -> None:
            self._archive_observe(
                "archive_relink_operation",
                "failed",
                key,
                archive_result="unavailable",
            )
            self._archive_relink_operation = None
            show(proposal, pending_state="unavailable")
            status.set(
                "The files could not be checked. Return to Library and try again."
            )

        def verified(result: Any) -> None:
            if result.error or result.value is None:
                verification_failed()
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
            unresolved = len(preview.entries) - len(ready)
            summary = (
                f"{len(ready)} {'file' if len(ready) == 1 else 'files'} ready"
                if ready
                else "No files ready"
            )
            if unresolved:
                summary += f" · {unresolved} {'item needs' if unresolved == 1 else 'items need'} attention"
            status.set(
                summary
                + "\nReview your selected files. Their location and saved details are checked; identical content is not confirmed."
            )
            if ready:
                apply.configure(
                    state="normal",
                    text="Update location"
                    if len(ready) == 1
                    else f"Update {len(ready)} locations",
                    command=lambda: self._archive_apply_relink(
                        preview, history, ready, status, apply, cancel
                    ),
                )

        def verification_timed_out() -> None:
            self._archive_observe("archive_relink_operation", "timed_out", key)
            self._archive_relink_operation = None
            show(proposal, pending_state="timed_out")
            status.set(
                "Checking these files took too long. Return to Library and try again."
            )

        if not self._archive_submit(
            "relink_verify",
            lambda cancelled: verify_relink(proposal, history, cancelled=cancelled),
            verified,
            on_timeout=verification_timed_out,
        ):
            verification_failed()
        panel._archive_reveal.start(
            lambda: review_surface.winfo_height() == int(review_surface.cget("height"))
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
            self._archive_relink_operation = None
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
        status.set("Saving the new file locations…")

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
            cancel.configure(state="normal", text="Back to Library")
            if result.error or result.value is None:
                if (
                    not result.error
                    and result.value is None
                    and self.__dict__.get("_archive_commit_cancel_reason")
                ):
                    # The worker can acknowledge cancellation before invoking
                    # work(), so no worker-side terminal observation was emitted.
                    self._archive_observe(
                        "archive_relink_operation",
                        "timed_out"
                        if self._archive_commit_cancel_reason == "timeout"
                        else "cancelled",
                        key,
                    )
                self._archive_relink_operation = None
                if not self._archive_flush_history():
                    status.set(
                        "No locations were updated. Other Library changes need to be recovered before you can edit again."
                    )
                    return
                cancelled = result.error == "RelinkCancelled" or (
                    not result.error
                    and self.__dict__.get("_archive_commit_cancel_reason")
                )
                status.set(
                    "The update took too long and was stopped. Your saved locations have not changed."
                    if cancelled and self._archive_commit_cancel_reason == "timeout"
                    else "Update cancelled. Your saved locations have not changed."
                    if cancelled
                    else "No locations were updated. Return to Library and choose the files again."
                )
                return
            self._archive_relink_operation = None
            self.download_history = result.value
            if not self._archive_flush_history():
                status.set(
                    "Locations updated. Other Library changes need to be recovered before you can edit again."
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
            self._archive_observe(
                "archive_relink_operation",
                "failed",
                key,
                archive_result="unavailable",
            )
            self._archive_relink_operation = None
            self._archive_commit_active = False
            self._archive_commit_status = None
            cancel.configure(state="normal", text="Back to Library")
            status.set("The update could not start. Return to Library and try again.")

    def _archive_show_inspector(self: Any) -> None:
        scene = self.__dict__.get("library_scene")
        if scene is not None:
            index = self.video_tree.model.selected_index()
            if index is not None:
                self._archive_reveal_library_details(index)
                return
            if not self.__dict__.get("_legacy_archive_requested", False):
                return
        self._archive_usage("archive", "inspector_opened")
        self._archive_inspector_expanded = not self.__dict__.get(
            "_archive_inspector_expanded", False
        )
        self._apply_focus_layout(force=True)

    def _archive_arrange_actions(self: Any) -> None:
        """One action order across layout and folder/media subject transitions."""
        row = self.focus_library_action_row
        desired = []
        folder = self.__dict__.get("_archive_folder_identity", False)
        browser = self.__dict__.get("video_tree")
        media = not folder and bool(browser is not None and browser.selection())
        subject = (
            folder or media or self.__dict__.get("_archive_inspector_expanded", False)
        )
        if media:
            desired.append(self.focus_library_play_button)
        if subject and not self.__dict__.get("_archive_details_page", False):
            desired.append(self.focus_library_details_button)
        if media:
            desired.append(self.focus_library_menu_button)
        if row.pack_slaves() == desired:
            return
        for button in row.pack_slaves():
            button.pack_forget()
        for index, button in enumerate(desired):
            button.pack(side="left", padx=(0, 6 if index < len(desired) - 1 else 0))

    def _apply_archive_layout(self: Any, width: int, _height: int) -> None:
        scene = self.__dict__.get("library_scene")
        if scene is not None:
            if not self.__dict__.get("_legacy_archive_requested", False):
                self.focus_library_actions.grid_remove()
                self.focus_metadata_content.grid_remove()
                self.video_tree.navigation.grid_remove()
                self._library_scene_return.grid_remove()
                self.focus_library_view.columnconfigure(0, minsize=0)
                scene.grid(row=0, column=0, rowspan=3, columnspan=2, sticky="nsew")
                return
            scene.grid_remove()
            self.focus_metadata_content.grid()
            self._library_scene_return.grid(row=2, column=1, sticky="w", pady=8)
        expanded = self.__dict__.get("_archive_inspector_expanded", False)
        compact = width < 1260
        detail_page = compact and expanded
        self._archive_details_page = detail_page
        if detail_page:
            # An intentionally bounded reading page replaces the browse grid.
            # Keeping one width for identity, tabs and facts avoids a thin rail
            # floating at the left of an otherwise empty compact window.
            inset = max(28, (width - 1040) // 2)
            self.focus_library_actions.grid_remove()
            self.focus_metadata_content.grid_configure(
                padx=(inset, inset), pady=(12, 16)
            )
            self.focus_archive_inspector_shell.configure(padding=0)
            self.focus_archive_identity_label.grid_remove()
            self.focus_archive_back_button.grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 16)
            )
            self.focus_selected_title_label.configure(font=(FONT_UI_FAMILY, 16, "bold"))
        else:
            self.focus_library_actions.grid()
            self.focus_metadata_content.grid_configure(padx=(0, 18), pady=(0, 14))
            self.focus_archive_inspector_shell.configure(padding=(14, 0, 0, 0))
            self.focus_archive_back_button.grid_remove()
            self.focus_archive_identity_label.grid()
            self.focus_selected_title_label.configure(font="")
        self.focus_archive_inspector_shell.columnconfigure(
            1, weight=1 if detail_page else 0
        )
        self.focus_archive_inspector_shell.columnconfigure(
            0, weight=0 if detail_page else 1, minsize=288 if detail_page else 0
        )
        self.focus_archive_inspector_shell.rowconfigure(
            0, weight=1 if detail_page else 0
        )
        self.focus_archive_inspector_shell.rowconfigure(
            1, weight=0 if detail_page else 1
        )
        self.focus_archive_identity.grid_configure(
            sticky="new" if detail_page else "ew", padx=(0, 28) if detail_page else 0
        )
        self.focus_archive_inspector.grid_configure(
            row=0 if detail_page else 1,
            column=1 if detail_page else 0,
            pady=(48, 0) if detail_page else 0,
        )
        if detail_page:
            self.focus_selected_overview.grid_configure(columnspan=2, pady=(0, 16))
            self.focus_thumbnail_wrap.grid_configure(
                row=0, column=0, rowspan=1, columnspan=2, sticky="nw"
            )
            self.focus_selected_title_label.grid_configure(
                row=1, column=0, columnspan=2, padx=0, pady=(14, 0)
            )
            self.focus_selected_meta_label.grid_configure(
                row=2, column=0, columnspan=2, padx=0, pady=(6, 0)
            )
            self.focus_selected_location_label.grid_configure(
                row=3, column=0, columnspan=2, padx=0, pady=(6, 0)
            )
            self.focus_library_action_row.grid(
                in_=self.focus_archive_identity,
                row=2,
                column=0,
                columnspan=2,
                sticky="w",
                padx=0,
                pady=(0, 4),
            )
            self.focus_library_details_button.pack_forget()
        elif expanded:
            self.focus_selected_overview.grid_configure(columnspan=2, pady=(0, 8))
            self.focus_library_action_row.grid(
                in_=self.focus_archive_identity,
                row=2,
                column=0,
                sticky="w",
                columnspan=2,
                padx=0,
                pady=(0, 4),
            )
        else:
            self.focus_library_action_row.grid(
                in_=self.focus_library_actions,
                row=0,
                column=1,
                columnspan=1,
                sticky="e",
                padx=0,
                pady=0,
            )
        if not detail_page:
            self.focus_thumbnail_wrap.grid_configure(
                row=0, column=0, rowspan=3, columnspan=1, sticky="nw"
            )
            for row, label in enumerate(
                (
                    self.focus_selected_title_label,
                    self.focus_selected_meta_label,
                    self.focus_selected_location_label,
                )
            ):
                label.grid_configure(
                    row=row,
                    column=1,
                    columnspan=1,
                    padx=(12, 0),
                    pady=(0 if row == 0 else 4, 0),
                )
        if self.__dict__.get("_archive_folder_identity"):
            self.focus_thumbnail_wrap.grid_remove()
        self.focus_library_action_row.lift()
        if compact and expanded:
            self.focus_library_filters.grid_remove()
            self.video_tree.navigation.grid_remove()
            self.focus_library_view.columnconfigure(0, minsize=0)
        else:
            self.focus_library_filters.grid()
            self.video_tree.navigation.grid()
            self.focus_library_view.columnconfigure(0, minsize=176)
        self.focus_library_category_filter.set_compact(compact)
        self.focus_library_search_field.set_compact(compact)
        self.focus_library_details_button.configure(
            text="Back to Library"
            if compact and expanded
            else "Hide details"
            if expanded
            else "Show details"
        )
        self._archive_arrange_actions()
        if compact:
            self.focus_metadata_content.columnconfigure(1, weight=0, minsize=0)
            if expanded:
                self.focus_queue_panel.grid_remove()
                self.focus_archive_inspector_shell.grid(
                    row=0, column=0, columnspan=2, sticky="nsew"
                )
            else:
                self.focus_archive_inspector_shell.grid_remove()
                self.focus_queue_panel.grid(
                    row=0, column=0, columnspan=2, sticky="nsew", padx=0
                )
        elif expanded:
            self.focus_metadata_content.columnconfigure(1, weight=0, minsize=350)
            self.focus_queue_panel.grid(
                row=0, column=0, columnspan=1, sticky="nsew", padx=(0, 18)
            )
            self.focus_archive_inspector_shell.grid(
                row=0, column=1, columnspan=1, sticky="nsew"
            )

        else:
            self.focus_metadata_content.columnconfigure(1, weight=0, minsize=0)
            self.focus_archive_inspector_shell.grid_remove()
            self.focus_queue_panel.grid(
                row=0, column=0, columnspan=2, sticky="nsew", padx=0
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
        self: Any, info: Any, *, accepted: Any = None, queue_token: Any = None
    ) -> None:
        import uuid

        from .media_player import resolve_library_media_path

        queue_owner = self.__dict__.get("watch_queue")
        if accepted is not None:
            queue_token = accepted.get("queue_token")
        if queue_token is not None:
            if queue_owner is None or not queue_owner.owns(queue_token):
                return
        elif accepted is None and queue_owner is not None:
            queue_owner.cancel()
        held = self.__dict__.get("_archive_queue_presentation")
        if held is not None and (queue_owner is None or not queue_owner.owns(held[0])):
            self.__dict__.pop("_archive_queue_presentation", None)
            held[1].close()
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
                "queue_token": queue_token,
            }
        existing = self.__dict__.get("_media_player_window")
        if existing is not None and not existing.closed and queue_token is None:
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
                if queue_owner is not None:
                    existing.set_queue_keys(None)
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
            if queue_token is not None and queue_owner is not None:
                host = existing.release_presentation_host(self._archive_cancel_playback)
                if host is not None:
                    self._archive_queue_presentation = (queue_token, host)
                with queue_owner.retiring_player():
                    existing.close()
            else:
                existing.close()
        self._media_player_launch_generation += 1
        generation = self._media_player_launch_generation
        self._archive_player_origin = accepted["origin"]
        operation = accepted["operation"]
        self._archive_finish_opening(
            self.__dict__.get("_archive_opening_operation"), "cancelled"
        )
        self._archive_opening_operation = operation
        self._archive_opening_queue_token = queue_token
        snapshot = dict(info)
        panel = self._archive_show_overlay(
            self._focus_views[self._archive_player_origin]
        )
        self._archive_playback_host = panel
        loading = ttk.Label(
            panel, text="Opening saved media…", style="FocusTitle.TLabel"
        )
        loading.grid(row=1, column=0, pady=24)
        ProductButton(
            panel,
            text="Back to browse",
            command=self._archive_cancel_playback,
            style="Media.FocusQuiet.TButton",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=12)
        panel._archive_reveal.start()

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
            if queue_token is not None and not queue_owner.owns(queue_token):
                self._archive_finish_opening(operation, "cancelled")
                return
            if result.error or result.value is None:
                from .failure_diagnostics import FailureDiagnostic

                self._fail_library_player_opening(
                    snapshot,
                    "The saved location could not be read. Reconnect the drive or update its location.",
                    FailureDiagnostic(reason="filesystem", stage="playback"),
                    operation=operation,
                    launch_generation=generation,
                    boundary="resolve",
                )
                return
            path, plan, image = result.value
            if path is None:
                from .failure_diagnostics import FailureDiagnostic

                self._archive_finish_opening(
                    operation,
                    "failed",
                    FailureDiagnostic(reason="filesystem", stage="playback"),
                    dimensions={"playback_failure_boundary": "resolve"},
                )
                self._archive_missing_media(snapshot, plan)
                return
            from .platform_services import find_runtime_executable

            ffmpeg = find_runtime_executable("ffmpeg")
            if not ffmpeg or self.playback_engine is None:
                from .failure_diagnostics import FailureDiagnostic

                self._fail_library_player_opening(
                    snapshot,
                    "The player is unavailable. Open the saved location to watch with another player, or reinstall VODForge.",
                    FailureDiagnostic(reason="dependency_missing", stage="playback"),
                    operation=operation,
                    launch_generation=generation,
                    boundary="dependency",
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
                queue_token=queue_token,
            )

        if not self._archive_submit(
            "playback_resolve",
            work,
            done,
            on_timeout=lambda: self._fail_library_player_opening(
                snapshot,
                "The saved location did not respond. Reconnect storage and try again.",
                operation=operation,
                launch_generation=generation,
                boundary="resolve",
                retry=True,
            ),
            on_cancel=lambda: self._archive_finish_opening(operation, "cancelled"),
        ):
            self._archive_finish_opening(operation, "cancelled")
            self._archive_restore_browser()

    def _archive_finish_opening(
        self: Any,
        operation: str | None,
        action: str,
        diagnostic: Any = None,
        *,
        dimensions: dict[str, str] | None = None,
    ) -> None:
        """Retire an opening intent once; a failed opening owns no live player."""
        if (
            operation is None
            or self.__dict__.get("_archive_opening_operation") != operation
        ):
            return
        self._record_playback_operation(
            operation, action, diagnostic, dimensions=dimensions
        )
        queue_owner = self.__dict__.get("watch_queue")
        queue_token = self.__dict__.pop("_archive_opening_queue_token", None)
        held = self.__dict__.get("_archive_queue_presentation")
        if held is not None and held[0] == queue_token:
            self.__dict__.pop("_archive_queue_presentation", None)
            held[1].close()
        if queue_owner is not None and queue_owner.owns(queue_token):
            queue_owner.cancel(
                "failed" if action == "failed" else "cancelled",
                failure_boundary=(dimensions or {}).get(
                    "playback_failure_boundary", "unknown"
                ),
                failure_reason=diagnostic.reason
                if diagnostic is not None
                else "open_failed",
                failure_detail=diagnostic,
            )
        self._archive_opening_operation = None
        self.__dict__.get("_archive_playback_origins", {}).pop(operation, None)

    def _archive_cancel_playback(self: Any) -> None:
        held = self.__dict__.pop("_archive_queue_presentation", None)
        if held is not None:
            held[1].close()
        if queue_owner := self.__dict__.get("watch_queue"):
            queue_owner.cancel()
        self._archive_retire_pending_playback()
        self._archive_finish_opening(
            self.__dict__.get("_archive_opening_operation"), "cancelled"
        )
        self._media_player_launch_generation += 1
        self._archive_cancel_work()
        existing = self.__dict__.get("_media_player_window")
        if existing is not None:
            existing.close()
        else:
            self._archive_restore_browser()

    def _archive_player_closed(self: Any) -> None:
        if queue_owner := self.__dict__.get("watch_queue"):
            queue_owner.player_closed()
        self._media_player_launch_generation += 1
        self._media_player_window = None
        self._media_player_source = None
        self._archive_poster_image = None
        if not self.__dict__.get("_closing"):
            self._archive_restore_browser()
            watch = self.__dict__.get("focus_watch")
            if watch is not None:
                watch._queue_render()

    def _archive_playback_error(
        self: Any,
        message: str,
        *,
        info: Any = None,
        retry: bool = False,
    ) -> None:
        panel = self._archive_playback_host
        for child in panel.winfo_children():
            child.destroy()
        ProductButton(
            panel,
            text="Back to browse",
            command=self._archive_cancel_playback,
            style="Media.FocusQuiet.TButton",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=12)
        ttk.Label(panel, text="Media needs attention", style="FocusTitle.TLabel").grid(
            row=1, column=0, sticky="w", padx=18, pady=10
        )
        panel.rowconfigure(2, weight=0)
        panel.rowconfigure(5, weight=1)
        ttk.Label(
            panel, text=message, style="Muted.TLabel", wraplength=780, justify="left"
        ).grid(row=2, column=0, sticky="nw", padx=18, pady=10)
        if info is not None:
            captured = dict(info)
            ttk.Label(
                panel,
                text=str(captured.get("title") or "Selected saved video"),
                style="FocusActiveTitle.TLabel",
                wraplength=780,
                justify="left",
            ).grid(row=3, column=0, sticky="w", padx=18, pady=(8, 12))
            actions = ttk.Frame(panel, style="FocusShell.TFrame")
            actions.grid(row=4, column=0, sticky="w", padx=18, pady=(0, 16))
            ProductButton(
                actions,
                text="Open saved location",
                command=lambda: self._open_selected_saved_location(captured),
                style="Media.Accent.TButton",
            ).pack(side="left", padx=(0, 10))
            if retry:
                ProductButton(
                    actions,
                    text="Try again",
                    command=lambda: (
                        self._archive_cancel_playback(),
                        self._play_selected_library_item(captured),
                    ),
                    style="Media.FocusQuiet.TButton",
                ).pack(side="left")

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

        ProductButton(
            actions, text="Locate moved file", command=locate, style="Accent.TButton"
        ).pack(side="left", padx=(0, 10))
        if prompt.primary_action == "redownload":
            ProductButton(
                actions,
                text=prompt.primary_label,
                command=lambda: (
                    self._archive_cancel_playback(),
                    self._accept_library_redownload(plan),
                ),
                style="Media.FocusQuiet.TButton",
            ).pack(side="left")
        elif prompt.primary_action == "open_forge":
            ProductButton(
                actions,
                text=prompt.primary_label,
                command=lambda: (
                    self._archive_cancel_playback(),
                    self._open_missing_media_in_forge(info, plan),
                ),
                style="Media.FocusQuiet.TButton",
            ).pack(side="left")

    def _archive_player_related_play(self: Any, record: Any) -> None:
        subject = resolve_archive_subject(self.metadata_items, record)
        if subject is None:
            self.status_var.set("That item is no longer in your Library.")
            return
        queue_owner = self.__dict__.get("watch_queue")
        if queue_owner is not None:
            from .watch_queue import QueueContinuity, queue_media_key

            current = self.__dict__.get("_media_player_window")
            continuity = (
                QueueContinuity(
                    current.playback.snapshot.volume,
                    current._unmuted_volume,
                    current._presentation_mode,
                )
                if current is not None
                else None
            )
            if queue_owner.jump(queue_media_key(subject[1]), continuity=continuity):
                return
        self._play_selected_library_item(dict(subject[1]))

    def _archive_player_details(self: Any, record: Any) -> None:
        if resolve_archive_subject(self.metadata_items, record) is None:
            self.status_var.set("That item is no longer in your Library.")
            return
        self._archive_cancel_playback()
        # Closing can reconcile the projection. Resolve the captured owner again.
        subject = resolve_archive_subject(self.metadata_items, record)
        if subject is None:
            self.status_var.set("That item is no longer in your Library.")
            return
        self._archive_reveal_library_details(subject[0])

    def _archive_watch_details(self: Any, index: int) -> None:
        self._archive_usage("watch", "details")
        self._archive_reveal_library_details(index)

    def _archive_reveal_library_details(self: Any, index: int) -> None:
        from_folders = self.__dict__.get("_legacy_archive_requested", False)
        if from_folders:
            self.video_tree.selection_set(str(index))
            self._display_selected_metadata(index)
        else:
            self._select_record_in_library({"metadata_index": index})
        self._select_focus_view("library")
        self._archive_inspector_expanded = True
        scene = self.__dict__.get("library_scene")
        if scene is not None:
            self._legacy_archive_requested = False
            if from_folders:
                values = tuple(self._archive_variant_choice.cget("values"))
                versions = tuple(
                    (archive_row_owner(self.metadata_items[item]), label)
                    for item, label in zip(
                        self._archive_variant_indices, values, strict=True
                    )
                )
                scene.show_details(
                    index,
                    on_return=lambda: self._library_scene_action("folders", None),
                    versions=versions,
                )
            else:
                scene.show_details(index)
        self._apply_focus_layout(force=True)

    def _archive_update_versions(self: Any, index: int) -> None:
        record = self.metadata_items[index]
        identity = (
            *media_source_identity(record),
            str(record.get("playlist_id") or ""),
        )
        component = next(
            (
                item
                for item in self.video_tree.model.components
                if index in item.indices
            ),
            None,
        )
        # Library cards group exports by source folder as well as media identity.
        # A version selector belongs to that card, not another saved copy elsewhere.
        candidates = component.indices if component is not None else (index,)
        indices = tuple(
            candidate
            for candidate in candidates
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
            index = indices[position]
            if not any(
                index in item.indices for item in self.video_tree.model.components
            ):
                # A queued selection can outlive filtering/removal. Keep the
                # current subject and restore its current choices without navigating.
                selected = self.video_tree.model.selected_index()
                if selected is not None:
                    self._archive_update_versions(selected)
                return
            self._archive_usage("archive", "version_selected")
            # Choosing an export version changes the selected subject, not the
            # user's folder/mode/page. Back must return to that same browse view.
            self.video_tree.selection_set(str(index))
            self._display_selected_metadata(index)
