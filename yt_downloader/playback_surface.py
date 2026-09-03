from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from collections.abc import Callable
from typing import Any

from .playback_backend import MediaPlayerError, NativeRenderSurface


class TkPlaybackSurfaceOwner:
    """Own one platform-native video child hosted inside a Tk stage."""

    def __init__(
        self,
        toplevel: tk.Misc,
        stage: tk.Widget,
        *,
        diagnostic: Callable[[str], None] | None = None,
    ) -> None:
        self.toplevel = toplevel
        self.stage = stage
        self._diagnostic = diagnostic or (lambda _message: None)
        self._closed = False
        self._view: Any | None = None
        self._surface: NativeRenderSurface | None = None
        self._last_frame: tuple[int, int, int, int] | None = None
        self._refresh_after_id: str | None = None
        if sys.platform == "darwin":
            self._surface = self._create_macos_surface()
        elif sys.platform == "win32":
            self.stage.update_idletasks()
            self._surface = NativeRenderSurface("hwnd", int(self.stage.winfo_id()))
        else:
            raise MediaPlayerError(
                "Internal playback is currently available on macOS and Windows."
            )
        self.stage.bind("<Configure>", self._configured, add="+")
        self.toplevel.bind("<Configure>", self._configured, add="+")

    @property
    def surface(self) -> NativeRenderSurface:
        if self._surface is None:
            raise MediaPlayerError("The internal playback surface is unavailable.")
        return self._surface

    def refresh(self) -> None:
        if self._closed or sys.platform != "darwin" or self._view is None:
            return
        try:
            self.toplevel.update_idletasks()
            x = self.stage.winfo_rootx() - self.toplevel.winfo_rootx()
            y = self.stage.winfo_rooty() - self.toplevel.winfo_rooty()
            width = max(1, self.stage.winfo_width())
            height = max(1, self.stage.winfo_height())
            frame = (x, y, width, height)
            if frame == self._last_frame:
                return
            parent_height = float(self._view.superview().bounds().size.height)
            self._view.setFrame_(((x, parent_height - y - height), (width, height)))
            self._last_frame = frame
        except Exception as exc:  # noqa: BLE001 - Cocoa bridge failures stay isolated
            self._diagnostic(
                f"native playback surface resize failed: {type(exc).__name__}"
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._refresh_after_id is not None:
            try:
                self.toplevel.after_cancel(self._refresh_after_id)
            except tk.TclError:
                pass
            self._refresh_after_id = None
        if self._view is not None:
            try:
                self._view.removeFromSuperview()
            except Exception as exc:  # noqa: BLE001 - Cocoa teardown is best effort
                self._diagnostic(
                    f"native playback surface teardown failed: {type(exc).__name__}"
                )
        self._view = None
        self._surface = None

    def _configured(self, _event: tk.Event[Any]) -> None:
        if self._closed or self._refresh_after_id is not None:
            return
        self._refresh_after_id = self.toplevel.after(16, self._commit_refresh)

    def _commit_refresh(self) -> None:
        self._refresh_after_id = None
        self.refresh()

    def _create_macos_surface(self) -> NativeRenderSurface:
        try:
            import objc  # type: ignore[import-untyped]
            from AppKit import NSView  # type: ignore[import-untyped]

            self.stage.update_idletasks()
            get_root_control = ctypes.CDLL(None).TkMacOSXGetRootControl
            get_root_control.argtypes = (ctypes.c_void_p,)
            get_root_control.restype = ctypes.c_void_p
            parent_pointer = int(get_root_control(int(self.stage.winfo_id())) or 0)
            if parent_pointer <= 0:
                raise RuntimeError("Tk returned no Cocoa content view")
            parent = objc.objc_object(c_void_p=parent_pointer)
            view = NSView.alloc().initWithFrame_(((0, 0), (1, 1)))
            parent.addSubview_(view)
            self._view = view
            self.refresh()
            return NativeRenderSurface("nsview", int(objc.pyobjc_id(view)))
        except Exception as exc:
            raise MediaPlayerError(
                "VODForge could not create its internal macOS playback surface."
            ) from exc
