"""Presentation changes reuse the player's existing backend and native surface."""

from __future__ import annotations

import logging
import math
import sys
import time
import tkinter as tk
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from .failure_diagnostics import capture_failure
from .playback_backend import MediaPlayerError


@dataclass
class PlayerPresentationHost:
    window: Any
    stage: Any
    mode: str
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.window.destroy()
        except tk.TclError:
            pass


class PlayerPresentationMixin:
    _closed: bool
    popup: Any
    _display_signature: tuple[bool, int, int] | None

    def _install_native_controls(self: Any) -> None:
        if not self.embedded or sys.platform != "darwin":
            return
        if self.__dict__.get("_native_overlay") is not None:
            return
        try:
            from .platforms.macos.player_overlay import MacOSPlayerOverlay

            self._native_overlay = MacOSPlayerOverlay(
                self._surface_owner, on_action=self._dispatch_overlay_action
            )
            self.transport.grid_remove()
            self._streaming_resize(
                SimpleNamespace(height=self._content_root.winfo_height())
            )
            self._native_surface_changed()
        except Exception:
            logging.getLogger(__name__).exception("Native player controls unavailable")
            self._on_feature("controls_fallback")
            overlay = self.__dict__.get("_native_overlay")
            if overlay is not None:
                overlay.close()
            self._native_overlay = None
            self.transport.grid()

    def _dispatch_overlay_action(self: Any, action: str, value: Any) -> None:
        # AppKit delegates must not call Tk, including after/after_idle: entering
        # Tcl from the native event callback can corrupt Tk's Python thread state.
        # The existing Tk-owned poll drains this bounded, same-thread queue.
        if self._closed:
            return
        pending = self._overlay_actions
        if (
            action in {"volume", "seek_fraction", "hover_fraction"}
            and pending
            and pending[-1][0] == action
        ):
            pending[-1] = (action, value)
        elif len(pending) < 64:
            pending.append((action, value))

    def _drain_overlay_actions(self: Any) -> None:
        pending = self.__dict__.get("_overlay_actions")
        if pending is None or self.__dict__.get("_draining_overlay_actions"):
            return
        self._draining_overlay_actions = True
        try:
            while pending and not self._closed:
                action, value = pending.popleft()
                try:
                    self._run_overlay_action(action, value)
                except Exception as exc:
                    logging.getLogger(__name__).exception(
                        "Player control action failed"
                    )
                    if not self._closed:
                        PlayerPresentationMixin._report_control_failure(
                            self, action, exc
                        )
                        PlayerPresentationMixin._set_control_notice(
                            self, "That playback option is unavailable right now."
                        )
        finally:
            self._draining_overlay_actions = False

    def _run_overlay_action(self: Any, action: str, value: Any) -> None:
        if self._closed:
            return
        if action in {"hover_fraction", "hover_end"}:
            PlayerPresentationMixin._handle_hover_preview(self, action, value)
            return
        if action in {"controls_shown", "controls_hidden"}:
            self._on_feature(action)
            return
        self._control_notice = ""
        if action == "toggle":
            self._toggle()
        elif action == "seek_fraction":
            self._seek_to(self.playback.snapshot.duration * min(1.0, max(0.0, value)))
        elif action in {"volume", "mute"}:
            current = self.playback.snapshot.volume
            if action == "mute":
                if current:
                    self._unmuted_volume = current
                value = 0 if current else self._unmuted_volume
            self.volume_var.set(round(value))
            self._schedule_volume("")
        elif action == "fullscreen":
            if self._presentation_mode == "fullscreen":
                self._return_presentation()
            else:
                self._open_presentation("fullscreen")
        elif action == "floating":
            self._open_presentation("floating")
        elif action == "return":
            self._return_presentation()
        elif action in {"fit", "fill"}:
            if action == "fill" and (
                self.__dict__.get("_captions_active", False)
                or self.__dict__.get("_caption_request", -1) >= 0
            ):
                PlayerPresentationMixin._set_control_notice(
                    self, "Turn captions off to fill the frame."
                )
                self._on_feature("caption_fill_unavailable")
                return
            old = self._video_fill
            self._video_fill = action == "fill"
            if self._apply_video_layout(report_failure=True):
                if action == "fit":
                    self._caption_restore_fill = False
                    self._caption_safety_blocked = False
                self._on_feature(action)
            else:
                self._video_fill = old
        elif action in {"backward", "forward"}:
            self._seek_relative(-10 if action == "backward" else 10)
        elif action.startswith("caption:"):
            try:
                PlayerPresentationMixin._select_caption_with_layout(
                    self, int(action.split(":", 1)[1])
                )
            except (MediaPlayerError, ValueError) as exc:
                PlayerPresentationMixin._set_control_notice(
                    self, "Captions could not be changed. Try again."
                )
                PlayerPresentationMixin._report_control_failure(self, action, exc)

    def _caption_layout(self: Any, *, fill: bool, origin: str) -> bool:
        previous = self._video_fill
        self._video_fill = fill
        try:
            applied = self._apply_video_layout()
        except Exception as exc:  # noqa: BLE001 - rollback native/provider state before diagnosis
            self._video_fill = previous
            PlayerPresentationMixin._report_control_failure(
                self, "fill" if fill else "fit", exc, origin=origin
            )
            return False
        if not applied:
            self._video_fill = previous
            error = self.__dict__.pop("_last_layout_error", None)
            if error is not None:
                PlayerPresentationMixin._report_control_failure(
                    self, "fill" if fill else "fit", error, origin=origin
                )
            return False
        self._on_feature("caption_fill_restored" if fill else "caption_fit_applied")
        return True

    def _select_caption_with_layout(self: Any, track: int) -> None:
        self._caption_safety_blocked = False
        fit_applied = False
        if track >= 0 and self.__dict__.get("_video_fill", False):
            if not PlayerPresentationMixin._caption_layout(
                self, fill=False, origin="caption_safety"
            ):
                PlayerPresentationMixin._set_control_notice(
                    self,
                    "Captions could not be turned on because the full video view is unavailable.",
                )
                return
            self._caption_restore_fill = True
            fit_applied = True
        # A provider may report no track while switching between enabled tracks.
        # Preserve the pending intent until it is acknowledged or superseded.
        previous_request = self.__dict__.get("_caption_request", -1)
        self._caption_request = track
        try:
            self.playback.select_caption_track(track)
        except (MediaPlayerError, ValueError):
            self._caption_request = previous_request
            if fit_applied:
                selected = getattr(self.playback, "selected_caption_track", None)
                try:
                    safe_to_restore = selected is None or selected() == -1
                except MediaPlayerError:
                    safe_to_restore = False
                if safe_to_restore:
                    self._caption_restore_fill = False
                    PlayerPresentationMixin._caption_layout(
                        self, fill=True, origin="caption_restore"
                    )
            raise
        self._on_feature("captions_selected")
        PlayerPresentationMixin._synchronize_caption_layout(self)
        if fit_applied:
            PlayerPresentationMixin._set_control_notice(
                self, "Showing the full video so captions stay readable.", seconds=3
            )

    def _synchronize_caption_layout(self: Any) -> None:
        selected = getattr(self.playback, "selected_caption_track", None)
        if selected is None:
            return
        try:
            actual_track = selected()
        except MediaPlayerError:
            return
        active = actual_track >= 0
        request = self.__dict__.get("_caption_request")
        off_confirmed = request == -1 and not active
        if request == actual_track:
            self.__dict__.pop("_caption_request", None)
        pending_on = self.__dict__.get("_caption_request", -1) >= 0
        was_active = self.__dict__.get("_captions_active", False)
        self._captions_active = active
        if not active:
            self._caption_safety_blocked = False
        if active and self.__dict__.get("_video_fill", False):
            if self.__dict__.get("_caption_safety_blocked", False):
                return
            if PlayerPresentationMixin._caption_layout(
                self, fill=False, origin="caption_safety"
            ):
                self._caption_restore_fill = True
                PlayerPresentationMixin._set_control_notice(
                    self, "Showing the full video so captions stay readable.", seconds=3
                )
            else:
                # The provider may begin with subtitles already enabled. Keep
                # playback safe if the renderer cannot switch to the full view.
                self._caption_restore_fill = False
                self._caption_safety_blocked = True
                try:
                    self.playback.select_caption_track(-1)
                    self._captions_active = selected() >= 0
                    if self._captions_active:
                        self.playback.pause()
                    PlayerPresentationMixin._set_control_notice(
                        self,
                        "The full video view is unavailable. Captions are off."
                        if not self._captions_active
                        else "Captions could not be displayed safely. Playback is paused.",
                    )
                except MediaPlayerError as exc:
                    PlayerPresentationMixin._report_control_failure(
                        self, "caption:-1", exc, origin="caption_safety"
                    )
                    try:
                        self.playback.pause()
                    except MediaPlayerError as pause_error:
                        PlayerPresentationMixin._report_control_failure(
                            self, "toggle", pause_error, origin="caption_safety"
                        )
                    PlayerPresentationMixin._set_control_notice(
                        self,
                        "Captions may be cropped. The video view could not be changed.",
                    )
        elif (
            not active
            and not pending_on
            and (was_active or off_confirmed)
            and self.__dict__.get("_caption_restore_fill", False)
        ):
            self._caption_restore_fill = False
            if not PlayerPresentationMixin._caption_layout(
                self, fill=True, origin="caption_restore"
            ):
                PlayerPresentationMixin._set_control_notice(
                    self, "Captions are off. The video is staying in the full view."
                )

    def _handle_hover_preview(self: Any, action: str, value: Any) -> None:
        from .media_player_ui import format_playback_time
        from .player_hover_preview import PlayerHoverPreview

        hover = self.__dict__.get("_hover_preview")
        if action == "hover_end":
            if hover is not None:
                hover.hide()
            self._hover_second = None
            return
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return
        snapshot = self.playback.snapshot
        if (
            snapshot.path is None
            or not math.isfinite(snapshot.duration)
            or snapshot.duration <= 0
        ):
            return
        if hover is None:
            hover = self._hover_preview = PlayerHoverPreview(self.previews)
        # Duration names the end boundary, where no frame exists. The hover
        # coordinator samples whole seconds, so cap just inside that boundary.
        position = min(
            snapshot.duration * min(1.0, max(0.0, value)),
            max(0.0, snapshot.duration - 0.001),
        )
        hover.request(snapshot.path, position)
        overlay = self.__dict__.get("_native_overlay")
        target = (snapshot.path, int(position))
        if overlay is not None and target != self.__dict__.get("_hover_second"):
            self._hover_second = target
            overlay.show_hover(format_playback_time(position))

    def _drain_hover_preview(self: Any) -> None:
        from .media_player_ui import format_playback_time

        hover = self.__dict__.get("_hover_preview")
        overlay = self.__dict__.get("_native_overlay")
        if self._closed or hover is None or overlay is None:
            return
        result = hover.poll()
        if result is None:
            return
        second, data = result
        shown = overlay.show_hover(format_playback_time(second), data)
        action = "hover_preview_shown" if shown else "hover_preview_unavailable"
        observed = self.__dict__.setdefault("_hover_observed", set())
        if action not in observed:
            observed.add(action)
            self._on_feature(action)

    def _report_control_failure(
        self: Any, action: str, error: BaseException, *, origin: str = "user"
    ) -> None:
        # Reuse the playback operation and consent/outbox owner. Never send
        # caption IDs, labels, paths, native messages or arbitrary action text.
        control = (
            "captions"
            if action.startswith("caption:")
            else {
                "fit": "fit",
                "fill": "fill",
                "fullscreen": "fullscreen",
                "floating": "floating",
                "return": "return",
                "toggle": "toggle",
                "seek_fraction": "seek",
                "backward": "seek",
                "forward": "seek",
                "volume": "volume",
                "mute": "volume",
            }.get(action, "unknown")
        )
        mode = self.__dict__.get("_presentation_mode", "embedded")
        mode = mode if mode in {"embedded", "fullscreen", "floating"} else "unknown"
        count = self.__dict__.get("_control_failure_count", 0)
        if count >= 8:
            return
        self._control_failure_count = count + 1
        try:
            self._on_feature("control_failed")
        except Exception:  # noqa: BLE001, S110  # nosec B110 - observation must not alter playback
            pass
        observe = self.__dict__.get("_on_operation")
        if observe is not None:
            try:
                observe(
                    "control_failed",
                    capture_failure(error, stage="playback", inspect_text=False),
                    dimensions={
                        "playback_control": control,
                        "playback_view": mode,
                        "playback_control_origin": origin
                        if origin in {"user", "caption_safety", "caption_restore"}
                        else "user",
                        "control_failure_kind": (
                            "provider_error"
                            if isinstance(error, MediaPlayerError)
                            else "unexpected_error"
                        ),
                    },
                )
            except Exception:  # noqa: BLE001, S110  # nosec B110 - optional diagnostics cannot break controls
                pass

    def _native_menu_entries(
        self: Any, *, captions: bool
    ) -> list[tuple[str, str, bool, bool]]:
        if captions:
            try:
                tracks = self.playback.caption_tracks()
                selected = self.playback.selected_caption_track()
                entries = (
                    [
                        ("Off", "caption:-1", selected == -1, bool(tracks)),
                        *(
                            (
                                label or f"Caption track {index}",
                                f"caption:{index}",
                                selected == index,
                                True,
                            )
                            for index, label in tracks
                        ),
                    ]
                    if tracks
                    else [("No captions in this video", "", False, False)]
                )
            except MediaPlayerError:
                entries = [("Captions are unavailable", "", False, False)]
        else:
            captions_need_fit = (
                self.__dict__.get("_captions_active", False)
                or self.__dict__.get("_caption_request", -1) >= 0
            )
            entries = [
                ("Fit entire video", "fit", not self._video_fill, True),
                (
                    "Fill frame (turn captions off)"
                    if captions_need_fit
                    else "Fill frame (crop)",
                    "fill",
                    self._video_fill,
                    not captions_need_fit,
                ),
                (
                    "Return to main window"
                    if self._presentation_window is not None
                    else "Watch in floating window",
                    "return" if self._presentation_window is not None else "floating",
                    False,
                    True,
                ),
                ("Jump back 10 seconds", "backward", False, True),
                ("Jump forward 10 seconds", "forward", False, True),
            ]
        return entries

    def _apply_video_layout(self: Any, *, report_failure: bool = False) -> bool:
        surface = self.__dict__.get("_surface_owner")
        apply = getattr(self.playback, "set_video_layout", None)
        if surface is None or apply is None:
            return False
        width, height = surface.stage.winfo_width(), surface.stage.winfo_height()
        signature = (self._video_fill, width, height)
        if signature == self._display_signature:
            return True
        self._last_layout_error = None
        try:
            apply(fill=self._video_fill, width=width, height=height)
            self._display_signature = signature
            return True
        except MediaPlayerError as exc:
            self._last_layout_error = exc
            PlayerPresentationMixin._set_control_notice(
                self, "The video view could not be changed. Try again."
            )
            if report_failure:
                PlayerPresentationMixin._report_control_failure(
                    self, "fill" if self._video_fill else "fit", exc
                )
            return False

    def _native_surface_changed(self: Any) -> None:
        if self._closed:
            return
        overlay = self.__dict__.get("_native_overlay")
        if overlay is not None:
            overlay.sync()
        self._apply_video_layout()

    def _present_native_controls(self: Any, snapshot: Any) -> None:
        PlayerPresentationMixin._drain_overlay_actions(self)
        PlayerPresentationMixin._drain_hover_preview(self)
        overlay = self.__dict__.get("_native_overlay")
        if overlay is not None:
            PlayerPresentationMixin._synchronize_caption_layout(self)
            overlay.set_menus(
                self._native_menu_entries(captions=False),
                self._native_menu_entries(captions=True),
            )
            overlay.present(
                snapshot,
                time_text=self.time_var.get(),
                fullscreen=self._presentation_mode == "fullscreen",
                floating=self._presentation_mode == "floating",
                notice=PlayerPresentationMixin._native_status_message(self, snapshot),
            )

    def _set_control_notice(self: Any, message: str, *, seconds: float = 0) -> None:
        self._control_notice = message
        self._control_notice_until = time.monotonic() + seconds if seconds else 0
        self.status_var.set(message)

    def _native_status_message(self: Any, snapshot: Any) -> str:
        deadline = self.__dict__.get("_control_notice_until", 0)
        if deadline and time.monotonic() >= deadline:
            self._control_notice = ""
            self._control_notice_until = 0
        notice = self.__dict__.get("_control_notice", "")
        if notice:
            return str(notice)
        progress = self.__dict__.get("_progress_binding")
        if progress is not None and progress.notice:
            return str(progress.notice)
        if snapshot.error:
            return str(snapshot.error)
        volume = snapshot.volume_observation
        return (
            "Volume is unavailable"
            if volume is not None and volume.disposition == "failed"
            else ""
        )

    def release_presentation_host(
        self: Any, on_cancel: Any
    ) -> PlayerPresentationHost | None:
        """Move the visible window across queue items without leaving fullscreen."""
        window = self.__dict__.get("_presentation_window")
        if window is None or self._surface_owner is None:
            return None
        host = PlayerPresentationHost(
            window, self._surface_owner.stage, self._presentation_mode
        )
        self._presentation_window, self._presentation_mode = None, "embedded"
        window.protocol("WM_DELETE_WINDOW", on_cancel)
        window.bind("<Escape>", lambda _event: on_cancel())
        for key in ("<space>", "<Left>", "<Right>"):
            window.unbind(key)
        return host

    def _open_presentation(
        self: Any, mode: str, host: PlayerPresentationHost | None = None
    ) -> None:
        if self._closed or self._surface_owner is None:
            if host is not None:
                host.close()
            return
        if self._presentation_window is not None:
            self._return_presentation()
        if host is None:
            window = tk.Toplevel(self.owner)
            window.withdraw()
            window.title("VODForge Player")
            window.configure(bg="#000000")
            window.geometry("720x405")
            window.minsize(480, 270)
            stage = tk.Frame(window, bg="#000000", bd=0, highlightthickness=0)
            stage.pack(fill="both", expand=True)
            if mode == "fullscreen":
                window.attributes("-fullscreen", True)
            else:
                window.attributes("-topmost", True)
            window.deiconify()
            window.update_idletasks()
        else:
            window, stage, mode = host.window, host.stage, host.mode
        window.protocol("WM_DELETE_WINDOW", self._return_presentation)
        window.bind("<Escape>", lambda _event: self._return_presentation())
        window.bind("<space>", lambda _event: self._toggle())
        window.bind("<Left>", lambda _event: self._seek_relative(-10))
        window.bind("<Right>", lambda _event: self._seek_relative(10))
        previous_top, previous_stage = (
            self._surface_owner.toplevel,
            self._surface_owner.stage,
        )
        try:
            self._surface_owner.rehost(window, stage)
        except Exception as exc:
            try:
                self._surface_owner.rehost(previous_top, previous_stage)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Player presentation restore failed"
                )
                self.close()
            finally:
                if host is not None:
                    host.close()
                else:
                    window.destroy()
            raise MediaPlayerError("The player could not open that view.") from exc
        self._presentation_window, self._presentation_mode = window, mode
        self._native_surface_changed()
        window.lift()
        window.focus_force()
        self._on_feature(mode)

    def _return_presentation(self: Any) -> None:
        window = self.__dict__.get("_presentation_window")
        if window is None or self._closed:
            return
        self._surface_owner.rehost(self.popup.winfo_toplevel(), self.stage)
        self._presentation_window, self._presentation_mode = None, "embedded"
        self._native_surface_changed()
        window.destroy()
        self.popup.focus_set()
        self._on_feature("returned")

    def _close_native_controls(self: Any) -> None:
        hover = self.__dict__.get("_hover_preview")
        if hover is not None:
            hover.close()
            self._hover_preview = None
        pending = self.__dict__.get("_overlay_actions")
        if pending is not None:
            pending.clear()
        overlay = self.__dict__.get("_native_overlay")
        if overlay is not None:
            overlay.close()
            self._native_overlay = None

    def _close_presentation_window(self: Any) -> None:
        window = self.__dict__.get("_presentation_window")
        if window is not None:
            self._presentation_window = None
            try:
                window.destroy()
            except tk.TclError:
                pass
