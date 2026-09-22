"""Contextual file actions using the existing archive worker and history authority."""

from __future__ import annotations

import copy
import tkinter as tk
import uuid
from collections import Counter
from collections.abc import Callable
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, cast

from .archive_file_operations import (
    FileOperationPlan,
    delete_files,
    keep_current_file_state,
    move_files,
    pending_file_operations,
    plan_file_operation,
    plan_move_operation,
    recover_move_cleanup,
)
from .archive_observations import bind_operation
from .archive_relink import record_fingerprint
from .history import HistoryError, history_archive_owner, load_history
from .platform_services import open_path, system_trash_available
from .product_telemetry import BoundProductOperation
from .ui_button_contract import ProductButton
from .ui_context_menu import ContextMenu
from .ui_layout import (
    bounded_window_size,
    centered_toplevel_geometry,
    window_logical_metrics,
)
from .ui_theme import FONT_UI, THEME
from .ui_widgets import ActionDialogSurface


class FileActionDialog:
    """One short decision, with protected actions and scoped keyboard behavior."""

    def __init__(self, master: Any, title: str, cancel: Callable[[], None]):
        self._recovery_buttons: tuple[ttk.Button, ...] = ()
        self.operation: BoundProductOperation | None = None
        self.action = ""
        self.stage = "analysis"
        self.finished = False
        self._cancel = cancel
        self.popup = tk.Toplevel(master)
        self.popup.title(title)
        self._metrics = window_logical_metrics(self.popup)
        px = self._metrics.px
        limit = bounded_window_size(
            self.popup.winfo_screenwidth(), self.popup.winfo_screenheight()
        )
        self.popup.geometry(
            centered_toplevel_geometry(master, 560, 340, target=self.popup)
        )
        self.popup.minsize(min(px(480), limit[0]), min(px(300), limit[1]))
        self.popup.configure(bg=THEME["bg"])
        self.popup.transient(master)
        self.surface = ActionDialogSurface(
            self.popup, padx=26, pady=24, modal=True, allow_body_scroll=True
        )
        self.heading = ttk.Label(
            self.surface.body,
            text=title,
            font=self._metrics.font((FONT_UI[0], 22, "bold")),
            wraplength=px(495),
            justify="left",
        )
        self.heading.pack(anchor="w", fill="x")
        self.message = tk.StringVar(self.popup, "Checking the selected files…")
        self.description = ttk.Label(
            self.surface.body,
            textvariable=self.message,
            style="Muted.TLabel",
            font=self._metrics.font(FONT_UI),
            wraplength=px(495),
            justify="left",
        )
        self.description.pack(anchor="w", fill="x", pady=(px(16), px(12)))
        self.note = tk.StringVar(self.popup, "")
        self.note_label = ttk.Label(
            self.surface.body,
            textvariable=self.note,
            style="Muted.TLabel",
            font=self._metrics.font(FONT_UI),
            wraplength=px(495),
            justify="left",
        )
        self.note_label.pack(anchor="w", fill="x")
        self.primary = ProductButton(
            self.surface.footer,
            text="Continue",
            style="Accent.TButton",
            state="disabled",
        )
        self.primary.pack(side="right")
        self.secondary = ProductButton(
            self.surface.footer,
            text="Cancel",
            style="FocusQuiet.TButton",
            command=cancel,
        )
        self.secondary.pack(side="right", padx=(0, px(10)))
        self.surface.bind_keys({"<Escape>": cancel})
        self.popup.protocol("WM_DELETE_WINDOW", cancel)
        self._stacked_actions = False
        self.surface.body.bind("<Configure>", self._resize, add="+")
        self.surface.body.bind("<Map>", self._resize, add="+")
        self.surface.footer.bind("<Configure>", self._resize, add="+")
        self.primary.bind("<Configure>", self._resize, add="+")

    def _resize(self, event: Any = None) -> None:
        if not self.surface.body.winfo_viewable():
            return
        width = self.surface.body.winfo_width()
        if width > 1:
            for label in (self.heading, self.description, self.note_label):
                if int(label.cget("wraplength")) != width:
                    label.configure(wraplength=width)
        footer_width = self.surface.footer.winfo_width()
        if footer_width <= 1:
            return
        gap = self._metrics.px(10)
        stacked = (
            self.primary.winfo_reqwidth() + self.secondary.winfo_reqwidth() + gap
            > footer_width
        )
        if stacked != self._stacked_actions:
            self._stacked_actions = stacked
            self.primary.pack_forget()
            self.secondary.pack_forget()
            self.primary.pack(side="top" if stacked else "right", anchor="e")
            self.secondary.pack(
                side="top" if stacked else "right",
                anchor="e",
                padx=0 if stacked else (0, gap),
                pady=(gap, 0) if stacked else 0,
            )

    def offer(
        self, label: str, callback: Callable[[], None], *, enabled: bool = True
    ) -> None:
        def invoke() -> None:
            if str(self.primary["state"]) != "disabled":
                callback()

        self.primary.configure(
            text=label, command=invoke, state="normal" if enabled else "disabled"
        )
        self._resize()
        self.surface.bind_keys({"<Return>": invoke, "<Escape>": self._cancel})

    def exists(self) -> bool:
        try:
            return bool(self.popup.winfo_exists())
        except tk.TclError:
            return False


class LibraryFileActionsMixin:
    _archive_worker: Any
    status_var: Any
    history_path: Path
    _archive_observe: Any
    _archive_submit: Any

    def _show_library_selection_actions(self: Any) -> None:
        owners = tuple(self.library_scene.selected_owners)
        if not owners:
            return
        previous = self.__dict__.get("_library_selection_menu")
        if previous is not None:
            previous.unpost()
            previous.destroy()
        menu = self._library_selection_menu = ContextMenu(self, tearoff=False)
        menu.add_command(
            label="Add to Collection…",
            command=partial(
                self._show_library_collection_editor, captured_owners=owners
            ),
        )
        menu.add_separator()
        menu.add_command(
            label="Move to…",
            command=partial(self._begin_library_file_action, "move", owners),
        )
        menu.add_command(
            label="Delete…",
            command=partial(self._begin_library_file_action, "delete", owners),
        )
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()
        # Keep this one menu until replacement/root teardown: Windows can queue
        # the selected callback after tk_popup returns.

    def _begin_library_file_action(
        self: Any, action: str, owners: tuple[str, ...]
    ) -> None:
        if (
            action not in {"move", "delete"}
            or not owners
            or self.__dict__.get("_archive_commit_active")
            or self.__dict__.get("_history_recovery_blocked")
        ):
            return
        if self._archive_worker.busy:
            self.status_var.set(
                "A storage check is finishing. Please try again shortly."
            )
            return
        destination = None
        if action == "move" and not self.__dict__.get("_archive_file_recovery_blocked"):
            chosen = filedialog.askdirectory(
                parent=cast(tk.Misc, self),
                title="Move selected media to",
                mustexist=True,
            )
            if not chosen:
                return
            destination = Path(chosen).resolve()
        previous = self.__dict__.get("_library_file_dialog")
        if previous is not None and previous.exists():
            previous.popup.lift()
            return
        dialog = FileActionDialog(
            self,
            "Move media" if action == "move" else "Delete media",
            lambda: self._cancel_library_file_dialog(dialog),
        )
        self._library_file_dialog = dialog
        history = copy.deepcopy(self.download_history)
        operation = bind_operation(
            self.__dict__.get("product_telemetry"),
            "library_file_operation",
            operation_key=str(uuid.uuid4()),
        )
        dialog.operation, dialog.action = operation, action
        dialog.stage = "analysis"
        self._archive_observe(
            "library_file_operation",
            "requested",
            operation,
            file_action=action,
            stage="analysis",
            item_count=str(len(owners)),
        )

        def work(cancelled: Any) -> Any:
            pending = pending_file_operations(
                self.history_path.parent / "file-operations"
            )
            if pending:
                return pending
            if action == "move" and destination is not None:
                return plan_move_operation(
                    history, owners, destination, cancelled=cancelled
                )
            return plan_file_operation(history, owners, cancelled=cancelled)

        def done(result: Any) -> None:
            if not dialog.exists():
                return
            if result.error or result.value is None:
                self._archive_observe(
                    "library_file_operation",
                    "needs_attention",
                    operation,
                    file_action=action,
                    stage="analysis",
                )
                dialog.message.set(
                    "The files could not be checked. Reconnect their storage and try again."
                )
                dialog.secondary.configure(text="Close")
                return
            if not isinstance(result.value, FileOperationPlan):
                self._show_file_recovery(dialog, result.value, operation)
                return
            plan = result.value
            counts = plan.counts
            ready, missing = counts.get("ready", 0), counts.get("missing", 0)
            eligible = ready + (missing if action == "delete" else 0)
            skipped = len(plan.items) - eligible
            if action == "move":
                dialog.heading.configure(
                    text=f"Move {ready} {'item' if ready == 1 else 'items'}?"
                )
                dialog.message.set(
                    f"Destination\n{destination}\n\nCollections and playback progress will follow your media."
                )
                primary, permanent = "Move", False
            else:
                lines = []
                permanent = not system_trash_available() and ready > 0
                if ready:
                    lines.append(
                        f"{ready} {'file' if ready == 1 else 'files'} will be "
                        + ("permanently deleted" if permanent else "moved to Trash")
                        + " and removed from Library."
                    )
                if missing:
                    lines.append(
                        f"{missing} {'file is' if missing == 1 else 'files are'} already missing. "
                        + (
                            "Only its Library entry will be removed."
                            if missing == 1
                            else "Only their Library entries will be removed."
                        )
                    )
                dialog.heading.configure(text="Delete selected media?")
                dialog.message.set(
                    "\n\n".join(lines) or "No files are ready to delete."
                )
                primary = (
                    "Continue…"
                    if permanent
                    else "Move to Trash"
                    if ready
                    else "Remove entries"
                )
            conflicts = counts.get("conflict", 0)
            dialog.note.set(
                f"{conflicts} destination conflicts. Those items will be kept."
                + (
                    f" {skipped - conflicts} other items could not be verified."
                    if skipped > conflicts
                    else ""
                )
                if conflicts
                else f"{skipped} {'item could' if skipped == 1 else 'items could'} not be verified and will be kept."
                if skipped
                else ""
            )
            dialog.offer(
                primary,
                lambda: self._commit_library_files(
                    dialog,
                    action,
                    plan,
                    history,
                    destination,
                    operation,
                    permanent=permanent,
                ),
                enabled=eligible > 0,
            )

        def timed_out() -> None:
            if not dialog.exists():
                return
            dialog.message.set("Storage did not respond. Reconnect it and try again.")
            self._archive_observe(
                "library_file_operation",
                "needs_attention",
                operation,
                file_action=action,
                stage="analysis",
            )

        if not self._archive_submit("file_preview", work, done, on_timeout=timed_out):
            dialog.popup.destroy()

    def _cancel_library_file_dialog(self: Any, dialog: FileActionDialog) -> None:
        if self.__dict__.get("_library_file_dialog") is not dialog:
            return
        if self.__dict__.get("_archive_commit_active"):
            self._archive_worker.cancel(retire_result=False)
            dialog.note.set("Stopping after the current safe step…")
            dialog.secondary.configure(state="disabled")
        else:
            self._archive_cancel_work()
            if not dialog.finished:
                self._archive_observe(
                    "library_file_operation",
                    "cancelled",
                    dialog.operation,
                    file_action=dialog.action,
                    stage=getattr(dialog, "stage", "analysis"),
                )
                dialog.finished = True
            if dialog.exists():
                dialog.popup.destroy()
            self._library_file_dialog = None

    def _commit_library_files(
        self: Any,
        dialog: FileActionDialog,
        action: str,
        plan: FileOperationPlan,
        history: Any,
        destination: Path | None,
        operation: BoundProductOperation | None,
        *,
        permanent: bool,
    ) -> None:
        if tuple(map(record_fingerprint, self.download_history)) != plan.snapshot:
            dialog.message.set(
                "The Library changed. Close this window and review the selection again."
            )
            dialog.primary.configure(state="disabled")
            return
        if permanent and not messagebox.askyesno(
            "Permanently delete files?",
            f"Permanently delete {plan.counts.get('ready', 0)} files from your computer?\n\n"
            "This cannot be undone. These files will not be sent to Trash.",
            parent=dialog.popup,
            default="no",
        ):
            return
        # A native confirmation runs a nested event loop; check history again.
        if tuple(map(record_fingerprint, self.download_history)) != plan.snapshot:
            dialog.message.set(
                "The selection changed. Review it again before continuing."
            )
            return
        journal_directory = self.history_path.parent / "file-operations"

        def work(cancelled: Any) -> Any:
            if action == "move":
                if destination is None:
                    raise ValueError("Choose a destination")
                return move_files(
                    plan,
                    history,
                    destination,
                    self.history_path,
                    journal_directory,
                    cancelled=cancelled,
                )
            return delete_files(
                plan,
                history,
                self.history_path,
                journal_directory,
                permanent=permanent,
                cancelled=cancelled,
            )

        removal_rows = tuple(
            dict(row)
            for row in self.metadata_items
            if action == "delete"
            and history_archive_owner(dict(row)) in {item.owner for item in plan.items}
        )
        self._run_library_file_commit(
            dialog, action, operation, work, removal_rows=removal_rows
        )

    def _run_library_file_commit(
        self: Any,
        dialog: FileActionDialog,
        action: str,
        operation: BoundProductOperation | None,
        work: Callable[..., Any],
        *,
        removal_rows: tuple[dict[str, Any], ...] = (),
    ) -> None:
        if self.__dict__.get("_archive_commit_active") or self._archive_worker.busy:
            return
        self._archive_commit_active = True
        dialog.stage = "commit"
        self._archive_commit_cancel_reason = ""
        dialog.secondary.configure(text="Cancel", state="normal")
        for button in getattr(dialog, "_recovery_buttons", ()):
            button.configure(state="disabled")
        dialog.primary.configure(state="disabled")
        dialog.note.set("")
        dialog.message.set(
            "Moving your media…" if action == "move" else "Updating your Library…"
        )
        self._archive_observe(
            "library_file_operation",
            "started",
            operation,
            file_action=action,
            stage="commit",
        )

        def done(result: Any) -> None:
            self._archive_commit_active = False
            # Always reload actual history, including when the worker's final
            # receipt write failed and no result object could be returned.
            try:
                self.download_history = load_history(self.history_path)
                pending = pending_file_operations(
                    self.history_path.parent / "file-operations"
                )
                self._archive_file_recovery_blocked = bool(pending)
            except (HistoryError, OSError, ValueError):
                self._history_recovery_blocked = True
                pending = ()
                self._archive_file_recovery_blocked = True
            if not self._archive_file_recovery_blocked:
                self._archive_flush_history()
            if not self.__dict__.get("_history_recovery_blocked"):
                from .library_state import resolve_library_removal_plan

                current_owners = {
                    history_archive_owner(row) for row in self.download_history
                }
                removed_runs: set[str] = set()
                for row in removal_rows:
                    if history_archive_owner(row) not in current_owners:
                        plan = resolve_library_removal_plan(
                            row, active_job=None, pending_jobs=[]
                        )
                        removed_runs.update(
                            self._apply_library_removal_plan(
                                row, -1, plan, history_committed=True
                            )
                        )
                if removed_runs:
                    self._reconcile_focus_after_library_removal(removed_runs)
            self._reconcile_library_projection()
            if self.__dict__.get("_closing") or not dialog.exists():
                return
            dialog.secondary.configure(text="Close", state="normal")
            if result.error or result.value is None or pending:
                self._archive_observe(
                    "library_file_operation",
                    "needs_attention",
                    operation,
                    file_action=action,
                    stage="commit",
                )
                if pending:
                    self._show_file_recovery(dialog, pending, operation)
                elif result.error == "FileOperationCapacityError":
                    dialog.message.set(
                        "This change needs more room to record safely. Select fewer items and try again. If it still cannot start, restart VODForge."
                    )
                else:
                    dialog.message.set(
                        "The change could not be confirmed. Your saved Library has been reloaded; review the files before trying again."
                    )
                return
            dialog.finished = True
            outcomes = Counter(state for _, state in result.value.outcomes)
            completed = outcomes.get("completed", 0)
            missing = outcomes.get("entry_removed", 0)
            kept = sum(outcomes.values()) - completed - missing
            dialog.heading.configure(
                text="Files kept as they are"
                if action == "recovery"
                else "Library updated"
            )
            dialog.message.set(
                "Your saved Library has been reloaded. No files were moved or deleted during this review."
                if action == "recovery"
                else (
                    f"Moved {completed} items."
                    if action == "move"
                    else f"Removed {completed} files and {missing} missing entries."
                )
                + (f" {kept} items were kept." if kept else "")
            )
            for child in getattr(dialog, "_recovery_buttons", ()):
                child.destroy()
            dialog._recovery_buttons = ()
            dialog.note.set("")
            self._archive_observe(
                "library_file_operation",
                "completed",
                operation,
                file_action=action,
                stage="commit",
                committed_count=str(completed + missing),
                skipped_count=str(kept),
            )
            scene = self.__dict__.get("library_scene")
            if scene is not None:
                scene._clear_selection()

        if not self._archive_submit("file_commit", work, done, deadline=False):
            self._archive_commit_active = False
            dialog.message.set(
                "Another storage check started. Close this window and try again."
            )

    def _show_file_recovery(
        self: Any,
        dialog: FileActionDialog,
        pending: Any,
        operation: BoundProductOperation | None,
    ) -> None:
        self._archive_file_recovery_blocked = True
        dialog.heading.configure(text="Review an interrupted change")
        dialog.message.set(
            "Some files may already have moved. Original copies may remain."
            if pending[0].action == "move"
            else "Some files may already be in Trash or have been deleted. Remaining Library entries have been kept."
        )
        dialog.note.set(
            "Review your files, then finish the change or keep things as they are."
        )
        if pending[0].can_finish:
            dialog.offer(
                "Finish move",
                lambda: self._recover_library_files(
                    dialog, pending[0].path, operation, finish=True
                ),
            )
        else:
            dialog.primary.configure(state="disabled")
        # Recovery-specific choices are confined to this dialog.
        for child in getattr(dialog, "_recovery_buttons", ()):
            child.destroy()
        keep = ProductButton(
            dialog.surface.body,
            text="Keep as is",
            style="FocusQuiet.TButton",
            command=lambda: self._recover_library_files(
                dialog, pending[0].path, operation, finish=False
            ),
        )
        keep.pack(anchor="w", pady=(dialog._metrics.px(12), 0))
        buttons = [keep]
        for label, path in pending[0].locations[:2]:
            button = ProductButton(
                dialog.surface.body,
                text=f"{label}: {path.name}",
                style="FocusQuiet.TButton",
                command=partial(self._review_file_location, path, dialog),
            )
            button.pack(anchor="w", pady=(dialog._metrics.px(8), 0))
            buttons.append(button)
        dialog._recovery_buttons = tuple(buttons)
        dialog.popup.geometry(
            centered_toplevel_geometry(self, 560, 460, target=dialog.popup)
        )

    def _review_file_location(self: Any, path: Path, dialog: FileActionDialog) -> None:
        try:
            open_path(path, create=False)
        except OSError:
            dialog.note.set(
                "This folder is unavailable. Reconnect its storage and try again."
            )

    def _show_library_file_recovery(self: Any) -> None:
        if self.__dict__.get("_closing") or not self.__dict__.get(
            "_archive_file_recovery_blocked"
        ):
            return
        if self._archive_worker.busy:
            self.after(500, self._show_library_file_recovery)
            return
        owners = tuple(history_archive_owner(row) for row in self.download_history)
        # A final receipt can fail after deleting the last history entry.
        self._begin_library_file_action("delete", owners or ("recovery",))

    def _recover_library_files(
        self: Any,
        dialog: FileActionDialog,
        receipt: Path,
        operation: BoundProductOperation | None,
        *,
        finish: bool,
    ) -> None:
        def work(cancelled: Any) -> Any:
            records = load_history(self.history_path)
            if finish:
                return recover_move_cleanup(
                    receipt, records, self.history_path, cancelled=cancelled
                )
            keep_current_file_state(receipt, records, self.history_path)
            from .archive_file_operations import FileOperationResult

            return FileOperationResult(tuple(records), (), receipt)

        self._run_library_file_commit(
            dialog, "move" if finish else "recovery", operation, work
        )
