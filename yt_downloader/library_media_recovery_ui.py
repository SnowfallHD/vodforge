from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Literal

from .library_media_recovery import LibraryMediaRecoveryPlan
from .run_identity import job_output_profile
from .ui_layout import centered_toplevel_geometry
from .ui_theme import THEME
from .ui_widgets import reveal_toplevel

MediaRecoveryAction = Literal["none", "open_forge", "redownload"]


@dataclass(frozen=True, slots=True)
class LibraryMediaRecoveryPrompt:
    """Immutable presentation copy derived from one recovery decision."""

    window_title: str
    heading: str
    message: str
    detail: str
    primary_label: str
    primary_action: MediaRecoveryAction
    show_cancel: bool = False


def library_media_recovery_prompt(
    plan: LibraryMediaRecoveryPlan,
) -> LibraryMediaRecoveryPrompt:
    """Describe a recovery plan without changing canonical run or Library state."""

    destination = str(plan.destination or "Saved location unavailable")
    if plan.kind == "unavailable":
        return LibraryMediaRecoveryPrompt(
            "Saved location unavailable",
            "Reconnect this saved location",
            "VODForge cannot access this item’s saved location right now. "
            "Reconnect the drive or network location, then try again.",
            destination,
            "Done",
            "none",
        )
    if plan.kind == "ambiguous":
        return LibraryMediaRecoveryPrompt(
            "Saved media needs attention",
            "VODForge found more than one possible file",
            "Open the saved location to identify the media manually. VODForge will "
            "not guess and risk playing or replacing the wrong file.",
            destination,
            "Done",
            "none",
        )
    if plan.kind == "legacy":
        return LibraryMediaRecoveryPrompt(
            "Media file not found",
            "This media was moved or deleted",
            "This older Library item does not contain its complete output profile. "
            "Open it in Forge with the original URL and destination so you can "
            "review the settings before downloading again.",
            destination,
            "Open in Forge",
            "open_forge",
            True,
        )
    if plan.can_redownload and plan.job is not None:
        return LibraryMediaRecoveryPrompt(
            "Media file not found",
            "This media was moved or deleted",
            "VODForge can download it again with the exact saved output profile and "
            "replace this Library item when the new file is ready.",
            f"{job_output_profile(plan.job)}\n{destination}",
            "Redownload",
            "redownload",
            True,
        )
    return LibraryMediaRecoveryPrompt(
        "Media file not found",
        "The saved redownload profile is invalid",
        "VODForge could not safely validate the output profile for this item. The "
        "Library entry has been left unchanged.",
        destination,
        "Done",
        "none",
    )


class LibraryMediaRecoveryDialog:
    """Own the missing-media prompt; callers only coordinate the chosen action."""

    def __init__(
        self,
        owner: tk.Tk,
        *,
        plan: LibraryMediaRecoveryPlan,
        on_action: Callable[[MediaRecoveryAction], None],
    ) -> None:
        self.owner = owner
        self.on_action = on_action
        self.prompt = library_media_recovery_prompt(plan)

        popup = tk.Toplevel(owner)
        popup.withdraw()
        popup.title(self.prompt.window_title)
        popup.transient(owner)
        popup.configure(bg=THEME["bg"])
        popup.resizable(False, False)
        self.popup = popup

        root = ttk.Frame(popup, style="FocusShell.TFrame")
        root.pack(fill="both", expand=True, padx=26, pady=24)
        root.columnconfigure(0, weight=1)

        ttk.Label(root, text=self.prompt.heading, style="FocusTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            root,
            text=self.prompt.message,
            style="Muted.TLabel",
            wraplength=480,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(7, 18))

        detail_shell = tk.Frame(root, bg=THEME["border"], bd=0)
        detail_shell.grid(row=2, column=0, sticky="ew")
        tk.Label(
            detail_shell,
            text=self.prompt.detail,
            bg=THEME["surface"],
            fg=THEME["muted"],
            wraplength=450,
            justify="left",
            padx=12,
            pady=10,
            bd=0,
            highlightthickness=0,
        ).pack(fill="x", padx=1, pady=1)

        actions = ttk.Frame(root, style="FocusShell.TFrame")
        actions.grid(row=3, column=0, sticky="e", pady=(20, 0))
        if self.prompt.show_cancel:
            ttk.Button(
                actions,
                text="Not now",
                command=self.popup.destroy,
                style="FocusQuiet.TButton",
            ).pack(side="left", padx=(0, 8))
        ttk.Button(
            actions,
            text=self.prompt.primary_label,
            command=self._accept,
            style=(
                "Accent.TButton"
                if self.prompt.primary_action != "none"
                else "FocusQuiet.TButton"
            ),
        ).pack(side="left")

        popup.protocol("WM_DELETE_WINDOW", popup.destroy)
        popup.bind("<Escape>", lambda _event: popup.destroy())

    def _accept(self) -> None:
        action = self.prompt.primary_action
        self.popup.destroy()
        if action != "none":
            self.on_action(action)

    def show(self) -> None:
        reveal_toplevel(
            self.popup,
            centered_toplevel_geometry(self.owner, width=560, height=330),
        )
        self.popup.grab_set()
        self.popup.focus_force()
