from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from tkinter import ttk
from typing import Literal

from .library_media_recovery import LibraryMediaRecoveryPlan
from .run_identity import job_output_profile
from .ui_button_contract import ProductButton
from .ui_layout import (
    bounded_window_size,
    centered_toplevel_geometry,
    window_logical_metrics,
)
from .ui_theme import FONT_UI_FAMILY, FONT_UI_SMALL, FONT_UI_SMALL_MEDIUM, THEME
from .ui_widgets import ActionDialogSurface, ProductEntry, reveal_toplevel

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
    output_settings: str | None = None


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
        preset_note = (
            " Everyday will be selected for this video because its saved preset has been retired."
            if plan.preset_migrated
            else ""
        )
        if plan.requires_destination_choice:
            return LibraryMediaRecoveryPrompt(
                "Media file not found",
                "Choose the download folder",
                "The original download root could not be confirmed. Choose a "
                "location. Your saved default media location will remain unchanged."
                + preset_note,
                "Choose a download folder",
                "Choose folder and open Forge",
                "open_forge",
                True,
                "Everyday • Review before downloading"
                if plan.preset_migrated
                else "Saved output settings require review",
            )
        return LibraryMediaRecoveryPrompt(
            "Media file not found",
            "This media was moved or deleted",
            "This older Library item does not contain its complete output profile. "
            "Open it in Forge with the original URL and destination so you can "
            "review the settings before downloading again." + preset_note,
            destination,
            "Open in Forge",
            "open_forge",
            True,
            "Everyday • Review before downloading"
            if plan.preset_migrated
            else "No saved output settings detected",
        )
    if plan.can_redownload and plan.job is not None:
        profile_message = (
            "Its older preset will use Everyday."
            if plan.preset_migrated
            else "Its saved output settings will be kept."
        )
        if plan.requires_destination_choice:
            return LibraryMediaRecoveryPrompt(
                "Media file not found",
                "Choose where to redownload",
                "Choose a download folder for this video. "
                + profile_message
                + " Your default location will remain unchanged.",
                "Choose a download folder",
                "Choose folder and redownload",
                "redownload",
                True,
                job_output_profile(plan.job),
            )
        return LibraryMediaRecoveryPrompt(
            "Media file not found",
            "This media was moved or deleted",
            (
                "VODForge will redownload only this video using Everyday because "
                "its saved preset has been retired."
                if plan.preset_migrated
                else "VODForge will redownload only this video with the exact saved output profile."
            )
            + " The other videos in its playlist will be left alone.",
            destination,
            "Redownload",
            "redownload",
            True,
            job_output_profile(plan.job),
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
        metrics = window_logical_metrics(popup)
        px = metrics.px
        limit_width, _ = bounded_window_size(
            popup.winfo_screenwidth(), popup.winfo_screenheight()
        )
        # This fixed-width dialog must establish text width before measuring
        # height; withdrawn widgets can report a1px Configure allocation.
        text_width = max(1, min(px(540), limit_width) - px(56))

        surface = ActionDialogSurface(popup, padx=26, pady=24)
        self.dialog_surface = surface
        root = surface.body
        root.columnconfigure(0, weight=1)

        ttk.Label(
            root,
            text=self.prompt.heading,
            style="FocusTitle.TLabel",
            font=metrics.font((FONT_UI_FAMILY, 18, "bold")),
            wraplength=text_width,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            root,
            text=self.prompt.message,
            style="Muted.TLabel",
            font=metrics.font(FONT_UI_SMALL),
            wraplength=text_width,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(px(7), px(18)))

        detail_shell = ttk.Frame(root, style="FocusShell.TFrame")
        detail_shell.grid(row=2, column=0, sticky="ew")
        detail_shell.columnconfigure(0, weight=1)
        if self.prompt.output_settings is not None:
            ttk.Label(
                detail_shell,
                text="Output settings",
                style="FocusEyebrow.TLabel",
                font=metrics.font(FONT_UI_SMALL_MEDIUM),
            ).grid(row=0, column=0, sticky="w")
            ttk.Label(
                detail_shell,
                text=self.prompt.output_settings,
                style="Muted.TLabel",
                font=metrics.font(FONT_UI_SMALL),
                wraplength=text_width,
                justify="left",
            ).grid(row=1, column=0, sticky="ew", pady=(px(5), px(16)))
        ttk.Label(
            detail_shell,
            text="Output path",
            style="FocusEyebrow.TLabel",
            font=metrics.font(FONT_UI_SMALL_MEDIUM),
        ).grid(row=2, column=0, sticky="w")
        self.path_variable = tk.StringVar(popup, self.prompt.detail)
        self.path_entry = ProductEntry(
            detail_shell, textvariable=self.path_variable, state="readonly"
        )
        self.path_entry.grid(row=3, column=0, sticky="ew", pady=(px(5), 0))

        actions = surface.footer
        actions.columnconfigure(0, weight=1)
        if self.prompt.show_cancel:
            ProductButton(
                actions,
                text="Not now",
                command=self.popup.destroy,
                style="FocusQuiet.TButton",
            ).grid(row=0, column=1, padx=(0, px(8)))
        ProductButton(
            actions,
            text=self.prompt.primary_label,
            command=self._accept,
            style=(
                "Accent.TButton"
                if self.prompt.primary_action != "none"
                else "FocusQuiet.TButton"
            ),
        ).grid(row=0, column=2)

        popup.protocol("WM_DELETE_WINDOW", popup.destroy)
        popup.bind("<Escape>", lambda _event: popup.destroy())

    def _accept(self) -> None:
        action = self.prompt.primary_action
        self.popup.destroy()
        if action != "none":
            self.on_action(action)

    def show(self) -> None:
        self.popup.update_idletasks()
        reveal_toplevel(
            self.popup,
            centered_toplevel_geometry(
                self.owner,
                width=540,
                height=self.popup.winfo_reqheight(),
                height_is_measured=True,
                target=self.popup,
            ),
        )
        self.popup.grab_set()
        self.popup.focus_force()
